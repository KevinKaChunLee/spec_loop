"""Synthesis stage: the synthesizer reads compact digests of the student's attempts at the training
tasks and revises the playbook; a script then removes lines specific to any task, training or test.

The leak check covers the held-out test tasks too: their gold patches and failing tests never
reach the synthesizer's inputs, and no line naming them survives in a playbook."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from lib import opencode_stream as ocs
from lib.common import die, load_state, log, prompt, read_json, sha256_bytes, state_update, timestamp, write_json, \
    write_text_atomic
from lib.opencode_runner import run_opencode

from .core import CFG, check_inputs, gold, iteration_stage, json_digest, model_for, opencode_bin, \
    opencode_config_json, playbook_path, stage_dir, tasks
from .env import DockerExecutor, LocalExecutor, container_name
from .evaluate import stage_attempts

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

Attempt = tuple[dict, Path, dict]


def _clip(text: str, limit: int) -> str:
    text = text or ""
    return text if len(text) <= limit else text[:limit] + f"\n... [{len(text) - limit} more characters]"


def _tail(path: str | None, limit: int) -> str:
    p = Path(path) if path else None
    if not p or not p.exists():
        return ""
    text = p.read_text(encoding="utf-8", errors="replace")
    return text if len(text) <= limit else f"[... {len(text) - limit} characters before]\n" + text[-limit:]


def attempts_by_task(run_id: str, stage: str) -> dict[str, list[Attempt]]:
    """{instance_id: [(attempt record, directory, evaluation or {})]} for `stage`."""
    out: dict[str, list[Attempt]] = {}
    for rec, d in stage_attempts(run_id, stage):
        out.setdefault(rec["instance_id"], []).append((rec, d, read_json(d / "eval.json") or {}))
    return out


def basis(run_id: str, stage: str) -> str:
    """Digest of what a synthesis from `stage` reads: its attempts' and the oracle's patches and
    outcomes. A playbook written from another basis is out of date."""
    return json_digest([(s, rec["instance_id"], rec["sample"], rec["patch_sha256"], ev.get("resolved"))
                        for s in (stage, "oracle") for atts in attempts_by_task(run_id, s).values()
                        for rec, _d, ev in atts])


def playbook_current(run_id: str, stage: str) -> bool:
    report = read_json(stage_dir(run_id, stage) / "playbook" / "leak_report.json") or {}
    return bool(report.get("ok")) and report.get("basis") == basis(run_id, stage)


def outcome(rec: dict, ev: dict) -> str:
    if not rec["valid"]:
        return "invalid (" + "; ".join(rec["problems"]) + ")"
    if ev.get("resolved") is None:
        return "not evaluated"
    if ev["resolved"]:
        return "RESOLVED"
    if not rec["patch_lines"]:
        return "unresolved: no change"
    if not ev.get("applied"):
        return "unresolved: the patch did not apply"
    return (f"unresolved: {len(ev.get('f2p_fail') or [])} of the issue's tests still fail, "
            f"{len(ev.get('p2p_fail') or [])} other tests broke")


def task_digest(run_id: str, task: dict, attempts: list[Attempt], oracle: list[Attempt]) -> str:
    lim = CFG["digest_limits"]
    out = [f"# {task['instance_id']} ({task.get('difficulty') or 'difficulty unknown'})", "", "## Outcome", ""]
    out += [f"- student attempt s{rec['sample']}: {outcome(rec, ev)}" for rec, _d, ev in attempts]
    out += [f"- stronger model s{rec['sample']}: {outcome(rec, ev)}" for rec, _d, ev in oracle] or \
        ["- stronger model: not run"]
    out += ["", "## Issue", "", _clip(task["problem_statement"], lim["problem_chars"]), ""]
    if not all(ev.get("resolved") for _r, _d, ev in attempts):
        out += ["## Correct patch (for you only; the student never sees it)", "", "```diff",
                _clip(gold(run_id, task["instance_id"])["patch"], lim["patch_chars"]), "```", ""]
    for rec, d, ev in attempts:
        out += [f"## Student attempt s{rec['sample']}: {outcome(rec, ev)}", ""]
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
    for rec, d, ev in oracle:
        if ev.get("resolved"):
            out += [f"## Stronger model s{rec['sample']} (resolved)", "", "Patch:", "", "```diff",
                    _clip((d / "patch.diff").read_text(encoding="utf-8"), lim["patch_chars"]), "```", "",
                    "Trajectory (one line per tool call):", ""]
            out += ocs.digest(ocs.parse(d / "trajectory.jsonl"), lim["trajectory_calls"])
            out.append("")
    return "\n".join(out) + "\n"


def summary(rows: list[tuple[dict, list[Attempt], list[Attempt]]]) -> str:
    out = ["# Training tasks and outcomes", "", "| task | difficulty | student | stronger model |", "|---|---|---|---|"]
    for task, attempts, oracle in rows:
        st = ", ".join(outcome(r, ev) for r, _d, ev in attempts)
        orc = ", ".join(outcome(r, ev) for r, _d, ev in oracle) or "not run"
        out.append(f"| {task['instance_id']} | {task.get('difficulty') or ''} | {st} | {orc} |")
    resolved = sum(1 for _t, a, _o in rows for _r, _d, ev in a if ev.get("resolved"))
    total = sum(len(a) for _t, a, _o in rows)
    return "\n".join(out) + f"\n\nThe student resolved {resolved} of {total} attempts.\n"


def leak_terms(run_id: str) -> dict:
    """Paths, defined names and failing-test names of every task's gold and test patches, and the
    normalised text of the gold patches, for the playbook check."""
    paths, names, texts = set(), set(), []
    for split in ("train", "test"):
        for t in tasks(run_id, split):
            g = gold(run_id, t["instance_id"])
            for patch in (g["patch"], g["test_patch"]):
                for p in DIFF_FILE_RE.findall(patch):
                    paths.add(p)
                    if Path(p).name not in GENERIC_BASENAMES:
                        paths.add(Path(p).name)
                names.update(n for n in DEF_RE.findall(patch) if len(n) >= CFG["playbook_limits"]["min_identifier"])
            texts.append(_norm("\n".join(line[1:] for line in g["patch"].splitlines()
                                         if line.startswith("+") and not line.startswith("+++"))))
            for test in g["FAIL_TO_PASS"]:
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
    prov = check_inputs(run_id, allow_drift, roles=("synthesizer",))
    backend = load_state(run_id)["backend"]
    stage = iteration_stage(k)
    by_task = attempts_by_task(run_id, stage)
    if not by_task:
        die(f"{stage} has no attempts to write a playbook from; run `iterate --start {k}`")
    oracle = attempts_by_task(run_id, "oracle")
    train = tasks(run_id, "train")
    rows = [(t, by_task.get(t["instance_id"], []), oracle.get(t["instance_id"], [])) for t in train]
    out_dir = stage_dir(run_id, stage) / "playbook"

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
    based_on = iteration_stage(k - 1) if k > 0 and playbook_path(run_id, iteration_stage(k - 1)).exists() else None
    if based_on:
        shutil.copy2(playbook_path(run_id, based_on), inputs / "previous_playbook.md")
    history = [f"## {iteration_stage(j)}\n\n" + p.read_text(encoding="utf-8")
               for j in range(k) if (p := stage_dir(run_id, iteration_stage(j)) / "playbook" / "changelog.md").exists()]
    if history:
        (inputs / "changelog_history.md").write_text("\n\n".join(history), encoding="utf-8")

    model = model_for("synthesizer")
    oc_cfg = opencode_config_json("synthesizer")
    name = container_name(run_id, stage, "synthesize")
    if backend == "local":
        ex = LocalExecutor(seed, Path(CFG["workspace_root"]) / run_id / stage / name, opencode_bin())
    else:
        ex = DockerExecutor(train[0]["image"], name, opencode_bin(), CFG["docker"], workdir="/work", seed=seed)
    pb_path, cl_path = f"{ex.workdir}/_outputs/playbook.md", f"{ex.workdir}/_outputs/changelog.md"
    terms = leak_terms(run_id)

    def run(text: str, label: str, resume: str | None = None) -> dict:
        return run_opencode(launch=lambda args: ex.launch(args, oc_cfg), model=model["id"], workdir=ex.workdir,
                            prompt=text, out_dir=out_dir, label=label, timeout_min=CFG["timeouts_min"]["synthesizer"],
                            completion_check=lambda: [] if ex.read(pb_path).strip()
                            else ["_outputs/playbook.md has not been written"],
                            max_nudges=CFG["completion_nudges"], kill_agent=ex.kill_agent, resume_session=resume)

    try:
        ex.start()
        meta = run(prompt("swe_synthesize.md", repo=train[0]["repo"], student=model_for("student")["id"],
                          n_tasks=str(len(rows)), max_lines=str(lim["max_lines"]), max_chars=str(lim["max_chars"])),
                   "trajectory")
        playbook = ex.read(pb_path)
        problems, flagged = check_playbook(playbook, terms)
        if (problems or flagged) and meta["session_id"]:
            log(f"{stage} playbook: {len(problems)} problem(s), {len(flagged)} flagged line(s); asking for a rewrite")
            listing = "\n".join([f"- {p}" for p in problems] +
                                [f"- line {e['line']}: {e['text'][:160]}  <- {'; '.join(e['reasons'])}" for e in flagged[:40]])
            run(FIX_PROMPT.format(problems=listing), "fix1", resume=meta["session_id"])
            playbook = ex.read(pb_path) or playbook
        changelog = ex.read(cl_path)
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
        write_text_atomic(playbook_path(run_id, stage), final)
    else:
        playbook_path(run_id, stage).unlink(missing_ok=True)
    write_text_atomic(out_dir / "changelog.md", changelog)
    report = {"ok": ok, "problems": problems, "removed": flagged, "lines": len(final.splitlines()),
              "chars": len(final), "sha256": sha256_bytes(final.encode("utf-8")) if ok else None,
              "based_on": based_on, "basis": basis(run_id, stage), "provenance": {**prov, "at": timestamp()},
              "written_at": timestamp()}
    write_json(out_dir / "leak_report.json", report)
    with state_update(run_id) as st:
        st.setdefault("playbooks", {})[stage] = {k_: report[k_] for k_ in ("ok", "lines", "chars", "sha256", "based_on")} \
            | {"stripped": len(flagged)}
    log(f"{stage} playbook: {'written' if ok else 'REJECTED (empty)'}, {report['lines']} lines"
        + (f", {len(flagged)} line(s) removed by the leak check" if flagged else ""))
    return report


def playbook_text(run_id: str, source_stage: str) -> str:
    path = playbook_path(run_id, source_stage)
    return path.read_text(encoding="utf-8") if path.exists() else ""
