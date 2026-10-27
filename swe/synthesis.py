"""Synthesis stage: the synthesizer reads compact digests of the student's attempts at the training
tasks and revises the playbook; a script then removes lines specific to any task, training or test.

The leak check covers the held-out test tasks too: their gold patches and failing tests never
reach the synthesizer's inputs, and no line naming them survives in a playbook."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from lib import opencode_stream as ocs
from lib.common import load_state, log, prompt, read_json, sha256_bytes, state_update, timestamp, write_json, \
    write_text_atomic
from lib.opencode_runner import opencode_config, run_opencode

from .core import CFG, api_key, base_url, check_inputs, gold, iteration_stage, model_for, opencode_bin, provenance, \
    stage_dir, tasks
from .env import DockerExecutor, LocalExecutor, config_json
from .evaluate import as_list, stage_attempts

FIX_PROMPT = """The playbook checker flagged `_outputs/playbook.md`:

{problems}

Rewrite `_outputs/playbook.md` so that it passes: refer to code by what it does or how to find it,
not by the paths and names of the training tasks' fixes and tests, and stay within the length limit.
Lines still flagged after this rewrite are removed automatically. Update `_outputs/changelog.md` to
match. Do not modify anything else."""
# Names too generic to identify a fix, even when a gold patch touches them.
GENERIC_BASENAMES = {"__init__.py", "models.py", "tests.py", "views.py", "admin.py", "forms.py", "urls.py",
                     "utils.py", "base.py", "fields.py", "options.py", "query.py", "sql.py", "apps.py"}
DIFF_FILE_RE = re.compile(r"^diff --git a/(\S+) b/", re.M)
DEF_RE = re.compile(r"^(?:[+-]\s*|@@[^@]*@@\s*.*?)(?:async\s+)?(?:def|class)\s+([A-Za-z_]\w*)", re.M)
TEST_NAME_RE = re.compile(r"\b(test_\w+)\b")
TEST_CLASS_RE = re.compile(r"\(([\w.]+)\)")


def _clip(text: str, limit: int) -> str:
    text = text or ""
    return text if len(text) <= limit else text[:limit] + f"\n... [{len(text) - limit} more characters]"


def _tail(path: str | None, limit: int) -> str:
    p = Path(path) if path else None
    if not p or not p.exists():
        return ""
    text = p.read_text(encoding="utf-8", errors="replace")
    return text if len(text) <= limit else f"[... {len(text) - limit} characters before]\n" + text[-limit:]


def outcome(ev: dict | None, rec: dict) -> str:
    if not rec["valid"]:
        return "invalid (" + "; ".join(rec["problems"]) + ")"
    if not ev or ev.get("resolved") is None:
        return "not evaluated"
    if ev["resolved"]:
        return "RESOLVED"
    if not rec["patch_lines"]:
        return "unresolved: no change"
    if not ev.get("applied"):
        return "unresolved: the patch did not apply"
    return (f"unresolved: {len(ev.get('f2p_fail') or [])} of the issue's tests still fail, "
            f"{len(ev.get('p2p_fail') or [])} other tests broke")


def task_digest(run_id: str, task: dict, attempts: list[tuple[dict, Path]], oracle: list[tuple[dict, Path]]) -> str:
    lim = CFG["digest_limits"]
    g = gold(run_id, task["instance_id"])
    evals = {rec["sample"]: read_json(d / "eval.json") for rec, d in attempts}
    out = [f"# {task['instance_id']} ({task.get('difficulty') or 'difficulty unknown'})", "", "## Outcome", ""]
    out += [f"- student attempt s{rec['sample']}: {outcome(evals[rec['sample']], rec)}" for rec, _d in attempts]
    o_ev = {rec["sample"]: read_json(d / "eval.json") for rec, d in oracle}
    out += [f"- stronger model s{rec['sample']}: {outcome(o_ev[rec['sample']], rec)}" for rec, _d in oracle] or \
        ["- stronger model: not run"]
    resolved_all = all((evals[r["sample"]] or {}).get("resolved") for r, _d in attempts)
    out += ["", "## Issue", "", _clip(task["problem_statement"], lim["problem_chars"]), ""]
    if not resolved_all:
        out += ["## Correct patch (for you only; the student never sees it)", "", "```diff",
                _clip(g.get("patch", ""), lim["patch_chars"]), "```", ""]
    for rec, d in attempts:
        ev = evals[rec["sample"]] or {}
        out += [f"## Student attempt s{rec['sample']}: {outcome(ev, rec)}", ""]
        if not ev.get("resolved"):
            patch = (d / "patch.diff").read_text(encoding="utf-8") if (d / "patch.diff").exists() else ""
            out += ["Patch:", "", "```diff", _clip(patch, lim["patch_chars"]) or "(no change)", "```", ""]
            if ev.get("f2p_fail") or ev.get("p2p_fail"):
                out += ["Hidden tests that failed: " + ", ".join((ev.get("f2p_fail") or []) + (ev.get("p2p_fail") or [])), ""]
            tail = _tail(ev.get("test_output"), lim["test_output_chars"])
            if tail:
                out += ["Test output (end):", "", "```", tail, "```", ""]
        out += ["Trajectory (one line per tool call):", ""]
        out += ocs.digest(ocs.parse(d / "trajectory.jsonl"), lim["trajectory_calls"]) or ["(no tool calls)"]
        out.append("")
    for rec, d in oracle:
        if (o_ev[rec["sample"]] or {}).get("resolved"):
            out += [f"## Stronger model s{rec['sample']} (resolved)", "", "Patch:", "", "```diff",
                    _clip((d / "patch.diff").read_text(encoding="utf-8"), lim["patch_chars"]), "```", "",
                    "Trajectory (one line per tool call):", ""]
            out += ocs.digest(ocs.parse(d / "trajectory.jsonl"), lim["trajectory_calls"])
            out.append("")
    return "\n".join(out) + "\n"


def summary(rows: list[tuple[dict, list, list]]) -> str:
    out = ["# Training tasks and outcomes", "", "| task | difficulty | student | stronger model |", "|---|---|---|---|"]
    for task, attempts, oracle in rows:
        st = ", ".join(outcome(read_json(d / "eval.json"), r) for r, d in attempts)
        orc = ", ".join(outcome(read_json(d / "eval.json"), r) for r, d in oracle) or "not run"
        out.append(f"| {task['instance_id']} | {task.get('difficulty') or ''} | {st} | {orc} |")
    resolved = sum(1 for _t, a, _o in rows for r, d in a if (read_json(d / "eval.json") or {}).get("resolved"))
    total = sum(len(a) for _t, a, _o in rows)
    return "\n".join(out) + f"\n\nThe student resolved {resolved} of {total} attempts.\n"


def leak_terms(run_id: str) -> dict:
    """Paths, defined names and failing-test names of every task's gold and test patches, and the
    normalised text of the gold patches, for the playbook check."""
    paths, names, texts = set(), set(), []
    for split in ("train", "test"):
        for t in tasks(run_id, split):
            g = gold(run_id, t["instance_id"])
            for patch in (g.get("patch", ""), g.get("test_patch", "")):
                for p in DIFF_FILE_RE.findall(patch):
                    paths.add(p)
                    if Path(p).name not in GENERIC_BASENAMES:
                        paths.add(Path(p).name)
                names.update(n for n in DEF_RE.findall(patch) if len(n) >= CFG["playbook_limits"]["min_identifier"])
            texts.append(_norm("\n".join(line[1:] for line in g.get("patch", "").splitlines()
                                         if line.startswith("+") and not line.startswith("+++"))))
            for test in as_list(g.get("FAIL_TO_PASS")):
                names.update(TEST_NAME_RE.findall(test))
                names.update(c.split(".")[-1] for c in TEST_CLASS_RE.findall(test))
    return {"paths": sorted(paths), "names": sorted(n for n in names if not n.startswith("__")), "text": "\n".join(texts)}


def _norm(text: str) -> str:
    return re.sub(r"[\s`*_#>|\-]+", "", text).lower()


def leak_lines(text: str, terms: dict) -> list[dict]:
    n = CFG["playbook_limits"]["ngram_chars"]
    name_re = re.compile(r"\b(" + "|".join(map(re.escape, terms["names"])) + r")\b") if terms["names"] else None
    flagged = []
    for no, line in enumerate(text.splitlines(), 1):
        reasons = [f"path {p}" for p in terms["paths"] if p in line]
        if name_re:
            reasons += [f"name {m}" for m in sorted(set(name_re.findall(line)))]
        norm = _norm(line)
        if len(norm) >= n and any(norm[i:i + n] in terms["text"] for i in range(0, len(norm) - n + 1, 4)):
            reasons.append("copied from a correct patch")
        if reasons:
            flagged.append({"line": no, "text": line.strip()[:200], "reasons": reasons})
    return flagged


def check_playbook(text: str, terms: dict) -> tuple[list[str], list[dict]]:
    lim = CFG["playbook_limits"]
    problems = []
    lines = text.splitlines()
    if not text.strip():
        problems.append("the playbook is empty")
    if len(lines) > lim["max_lines"]:
        problems.append(f"{len(lines)} lines; the limit is {lim['max_lines']}")
    if len(text) > lim["max_chars"]:
        problems.append(f"{len(text)} characters; the limit is {lim['max_chars']}")
    return problems, leak_lines(text, terms)


def strip_lines(text: str, numbers: list[int]) -> str:
    drop = set(numbers)
    return "\n".join(line for no, line in enumerate(text.splitlines(), 1) if no not in drop) + "\n"


def fit(text: str) -> str:
    """Cut a playbook that is still too long after its rewrite to the length limit, whole lines only."""
    lim = CFG["playbook_limits"]
    lines = text.splitlines()[: lim["max_lines"]]
    while lines and len("\n".join(lines)) + 1 > lim["max_chars"]:
        lines.pop()
    return "\n".join(lines) + "\n"


def synthesize(run_id: str, k: int, allow_drift: bool) -> dict:
    """Write the playbook from iteration k's attempts (used by iteration k + 1)."""
    served = check_inputs(run_id, allow_drift, roles=("synthesizer",))
    state = load_state(run_id)
    stage = iteration_stage(k)
    out_dir = stage_dir(run_id, stage) / "playbook"
    by_task: dict[str, list] = {}
    for rec, d in stage_attempts(run_id, stage):
        by_task.setdefault(rec["instance_id"], []).append((rec, d))
    oracle = {}
    for rec, d in stage_attempts(run_id, "oracle") if stage_dir(run_id, "oracle").exists() else []:
        oracle.setdefault(rec["instance_id"], []).append((rec, d))
    rows = [(t, by_task.get(t["instance_id"], []), oracle.get(t["instance_id"], [])) for t in tasks(run_id, "train")]

    seed = out_dir / "workspace"
    shutil.rmtree(seed, ignore_errors=True)
    inputs = seed / "_inputs"
    (inputs / "tasks").mkdir(parents=True)
    (seed / "_outputs").mkdir()
    (seed / "_outputs" / ".keep").write_text("", encoding="utf-8")
    (inputs / "summary.md").write_text(summary(rows), encoding="utf-8")
    for task, attempts, orc in rows:
        (inputs / "tasks" / f"{task['instance_id']}.md").write_text(task_digest(run_id, task, attempts, orc),
                                                                     encoding="utf-8")
    lim = CFG["playbook_limits"]
    (inputs / "playbook_rules.md").write_text(prompt("swe_playbook_rules.md", max_lines=str(lim["max_lines"]),
                                                     max_chars=str(lim["max_chars"])), encoding="utf-8")
    previous = stage_dir(run_id, iteration_stage(k - 1)) / "playbook" / "playbook.md" if k > 0 else None
    if previous and previous.exists():
        shutil.copy2(previous, inputs / "previous_playbook.md")
    history = [f"## {iteration_stage(j)}\n\n" + p.read_text(encoding="utf-8")
               for j in range(k) if (p := stage_dir(run_id, iteration_stage(j)) / "playbook" / "changelog.md").exists()]
    if history:
        (inputs / "changelog_history.md").write_text("\n\n".join(history), encoding="utf-8")

    model = model_for("synthesizer")
    oc_cfg = config_json(opencode_config(base_url("synthesizer"), [model], model["id"], api_key()))
    name = re.sub(r"[^a-zA-Z0-9_.-]", "-", f"swe-{run_id}-{stage}-synthesize")
    if state.get("backend") == "local":
        ex = LocalExecutor(seed, Path(CFG["workspace_root"]) / run_id / stage / name, opencode_bin())
    else:
        train = tasks(run_id, "train")
        ex = DockerExecutor(train[0]["image"], name, opencode_bin(), CFG["docker"], workdir="/work",
                            conda_activate=CFG["docker"]["conda_activate"], seed=seed)
    pb_path, cl_path = f"{ex.workdir}/_outputs/playbook.md", f"{ex.workdir}/_outputs/changelog.md"
    text = prompt("swe_synthesize.md", repo=rows[0][0]["repo"] if rows else "", student=model_for("student")["id"],
                  n_tasks=str(len(rows)), max_lines=str(lim["max_lines"]), max_chars=str(lim["max_chars"]))
    terms = leak_terms(run_id)
    ex.start()
    try:
        common = dict(launch=lambda args: ex.launch(args, oc_cfg), model=model["id"], workdir=ex.workdir,
                      out_dir=out_dir, timeout_min=CFG["timeouts_min"]["synthesizer"], kill_agent=ex.kill_agent,
                      completion_check=lambda: [] if (ex.read(pb_path) or "").strip()
                      else ["_outputs/playbook.md has not been written"], max_nudges=CFG["completion_nudges"])
        meta = run_opencode(prompt=text, label="trajectory", **common)
        playbook = ex.read(pb_path) or ""
        problems, flagged = check_playbook(playbook, terms)
        if (problems or flagged) and meta["session_id"]:
            log(f"{stage} playbook: {len(problems)} problem(s), {len(flagged)} flagged line(s); asking for a rewrite")
            listing = "\n".join([f"- {p}" for p in problems] +
                                [f"- line {e['line']}: {e['text'][:160]}  <- {'; '.join(e['reasons'])}" for e in flagged[:40]])
            run_opencode(prompt=FIX_PROMPT.format(problems=listing), label="fix1", resume_session=meta["session_id"],
                         **common)
            playbook = ex.read(pb_path) or playbook
        changelog = ex.read(cl_path) or ""
    finally:
        ex.stop()

    write_text_atomic(out_dir / "playbook.raw.md", playbook)
    problems, flagged = check_playbook(playbook, terms)
    final = fit(strip_lines(playbook, [e["line"] for e in flagged])) if playbook.strip() else ""
    ok = bool(final.strip())
    if flagged:
        changelog += "\n\n## Removed by the leak check\n\n" + "\n".join(
            f"- line {e['line']} ({'; '.join(e['reasons'])}): {e['text'][:120]}" for e in flagged) + "\n"
    if ok:
        write_text_atomic(out_dir / "playbook.md", final)
    else:
        (out_dir / "playbook.md").unlink(missing_ok=True)
    write_text_atomic(out_dir / "changelog.md", changelog)
    report = {"ok": ok, "problems": problems, "stripped": flagged, "lines": len(final.splitlines()),
              "chars": len(final), "sha256": sha256_bytes(final.encode("utf-8")) if ok else None,
              "based_on": iteration_stage(k - 1) if previous and previous.exists() else None,
              "provenance": provenance(run_id, served), "written_at": timestamp()}
    write_json(out_dir / "leak_report.json", report)
    with state_update(run_id) as st:
        st.setdefault("playbooks", {})[stage] = {k_: report[k_] for k_ in ("ok", "lines", "chars", "sha256", "based_on")} \
            | {"stripped": len(flagged)}
    log(f"{stage} playbook: {'written' if ok else 'REJECTED (empty)'}, {report['lines']} lines"
        + (f", {len(flagged)} line(s) removed by the leak check" if flagged else ""))
    return report


def playbook_text(run_id: str, source_stage: str) -> str:
    path = stage_dir(run_id, source_stage) / "playbook" / "playbook.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""
