#!/usr/bin/env python3
"""Oracle / student OpenSpec loop driven by the Cursor CLI.

Typical flow:
  loop.py prepare --run r1
  loop.py oracle  --run r1                   # oracle writes the reference spec
  # review runs/r1/oracle/spec/openspec/: edit it directly, and/or
  loop.py oracle  --run r1 --revise "..."    # resume the oracle session with feedback
  loop.py extract --run r1 --target oracle   # propose the reference decision table
  # review runs/r1/oracle/decisions.review.md, edit decisions.proposed.json if needed
  loop.py freeze  --run r1                   # hash spec + decisions, read-only; never change again
  loop.py iterate --run r1 --iters 3         # student -> compare -> synthesize, repeated
  loop.py status  --run r1

Single stages: `student`, `compare`, `synthesize` (all take --iter K).
`student --iter 0` may run before the freeze, since it needs nothing from the oracle.
Offline checks that touch neither state.json nor scores.csv: `rescore` (score an existing
student spec again), `leak-check` (run the playbook checks on a playbook), `extract`.

Plumbing test with a tiny task and the smoke model for every role:
  loop.py smoke --run smoke1

Every agent run is also exported for TrajViz under <stage>/trajviz/ (`<label>.trajviz.json`
to upload into the dashboard, `<label>.views/` and `<label>.html`); `loop.py trajviz --run r1`
re-exports existing runs.
"""

from __future__ import annotations

import argparse
import copy
import csv
import io
import json
import math
import re
import shutil
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from lib import decisions as dec
from lib import guards, render_traj, spec_metrics, trajviz_export, workspace
from lib.common import (PROMPTS, ROOT, copy_tree, die, git, iter_dir, load_config, load_state, log,
                        make_readonly, make_writable, prompt, read_json, remove_tree, run_dir,
                        save_state, sha256_bytes, sha256_file, write_json)
from lib.runner import run_agent, set_parallel_limit

CFG = load_config()
SCORING = CFG["scoring"]
DIMENSIONS = list(SCORING["weights"])
SEVERITIES = {"high", "medium", "low"}
TAGS = {"student_wrong", "student_defensible", "reference_questionable"}
SOFT_PARTS = {"requirements_correctness": "baseline_coverage", "scenario_quality": "testability_grounding",
              "design_quality": "code_level_design", "readability": "readability_rules"}
DECISIONS_FILE = "decisions.json"
CSV_FIELDS = ["iter", "sample", "total", "vs_best", *DIMENSIONS, "judges", "judge_spread", "code_share",
              "disputes", "gaps_student_wrong", "gaps_high", "gaps_closed", "gaps_reopened", "validate_ok",
              "leak_ok", "no_code_ok", "hmos_coverage", "subagents", "nudges", "input_tokens",
              "output_tokens", "duration_min", "model"]

REVISE_PROMPT = """A human reviewer read the OpenSpec you wrote in this workspace and asks for the changes below.
The files under openspec/ may also contain edits the reviewer made directly; keep those.
Apply the feedback, keep every rule of the original task (write only under openspec/, no questions,
zh-CN prose), and finish only when `openspec validate --all --strict` passes.

Reviewer feedback:

{feedback}
"""

FIX_PROMPT = """`_outputs/{name}` does not pass the checker:

{errors}

Fix `_outputs/{name}`{also}. Do not modify anything else.
"""

SYNTH_FIX_PROMPT = """The playbook checker rejected `_outputs/playbook.md`:

{problems}

Passages that overlap with the reference spec (normalized, whitespace and markdown removed):
{spans}

Lines that state a decision AGENTS.md leaves open, state a finding about what the HMOS code does,
or name HMOS identifiers or file names that AGENTS.md, config.yaml and the task do not name:
{leaks}

Rewrite `_outputs/playbook.md` so that it passes: shorten it, replace copied passages and stated answers
with instructions on how to find the information, refer to code by directory or by what to search for
instead of by name, and do not list the reference's capability ids. Flagged lines that remain after the
last rewrite are deleted automatically. Update `_outputs/changelog.md` to match. Do not modify anything else.
"""


# ---------------------------------------------------------------- helpers

def smoke(state: dict) -> bool:
    return bool(state.get("smoke"))


def model_for(state: dict, role: str) -> dict:
    return CFG["smoke_model"] if smoke(state) else CFG["models"][role]


def timeout_for(state: dict, role: str) -> float:
    return CFG["timeouts_min"]["smoke"] if smoke(state) else CFG["timeouts_min"][role]


def task_text(state: dict) -> str:
    name = "smoke_task.md" if smoke(state) else "task.md"
    return prompt(name, change_name=CFG["change_name"])


def base_dir(run_id: str) -> Path:
    return run_dir(run_id) / "base"


def hmos_index(run_id: str) -> dict:
    return spec_metrics.build_hmos_index(base_dir(run_id), CFG["hmos_dir"],
                                         run_dir(run_id) / "hmos_index.json")


def oracle_dir(run_id: str) -> Path:
    return run_dir(run_id) / "oracle"


def oracle_spec(run_id: str) -> Path:
    return oracle_dir(run_id) / "spec"


def manifest_text(spec_root: Path) -> str:
    lines = [f"{sha256_file(p)}  {p.relative_to(spec_root).as_posix()}"
             for p in sorted(spec_root.rglob("*")) if p.is_file()]
    return "\n".join(lines) + "\n"


def manifest_expected(run_id: str, state: dict) -> str:
    """MANIFEST.sha256: the frozen spec files, then the frozen reference decisions once they exist."""
    text = manifest_text(oracle_spec(run_id))
    if state.get("reference_decisions", {}).get("frozen"):
        text += f"{sha256_file(oracle_dir(run_id) / DECISIONS_FILE)}  {DECISIONS_FILE}\n"
    return text


def verify_frozen(run_id: str, state: dict) -> None:
    if not state.get("frozen"):
        die("the oracle spec is not frozen yet; review it and run `loop.py freeze`")
    manifest = oracle_dir(run_id) / "MANIFEST.sha256"
    if manifest_expected(run_id, state) != manifest.read_text(encoding="utf-8"):
        die(f"the frozen oracle spec or reference decisions changed since freeze ({manifest}); "
            f"restore them before continuing")


def reference_decisions(run_id: str, state: dict, allow_proposed: bool = False,
                        required: bool = True) -> dict | None:
    """The frozen reference decision table; with `allow_proposed`, the unconfirmed proposal."""
    frozen = oracle_dir(run_id) / DECISIONS_FILE
    if state.get("reference_decisions", {}).get("frozen") and frozen.exists():
        return read_json(frozen)
    proposed = oracle_dir(run_id) / "decisions.proposed.json"
    if allow_proposed and proposed.exists():
        log("warning: using the unconfirmed reference decisions (oracle/decisions.proposed.json); "
            "results are provisional")
        return read_json(proposed)
    if required:
        die(f"the reference decisions of run '{run_id}' are not frozen: run `loop.py extract --run {run_id} "
            f"--target oracle`, review oracle/decisions.review.md, then `loop.py freeze --run {run_id}`")
    return None


def run_checked_agent(state: dict, role: str, run_id: str, ws: Path, prompt_text: str, out_dir: Path,
                      name: str, check, retries: int, title: str, outputs: tuple[str, ...],
                      also: str = "") -> tuple:
    """Run an agent that writes the JSON file `_outputs/<name>`. `check(data)` returns
    (result, errors); while errors remain, the session is resumed with them (at most `retries`
    times). Returns the last (result, errors); result is None if the file never parsed."""
    model = model_for(state, role)
    meta = run_agent(model=model, ws=ws, prompt=prompt_text, out_dir=out_dir, label="trajectory",
                     timeout_min=timeout_for(state, role))
    result, errors = None, [f"_outputs/{name} was not written"]
    for attempt in range(retries + 1):
        path = ws / "_outputs" / name
        if path.exists():
            try:
                result, errors = check(json.loads(path.read_text(encoding="utf-8")))
            except json.JSONDecodeError as e:
                result, errors = None, [f"invalid JSON: {e}"]
        if not errors or not meta.get("session_id") or attempt == retries:
            break
        log(f"{title}: _outputs/{name} has {len(errors)} problem(s); asking for a fix")
        meta = run_agent(model=model, ws=ws, prompt=FIX_PROMPT.format(
            name=name, errors="\n".join(f"- {e}" for e in errors[:40]), also=also),
            out_dir=out_dir, label=f"fix{attempt + 1}", timeout_min=timeout_for(state, role),
            resume_session=meta["session_id"])
    finish_io_stage(run_id, ws, out_dir, outputs, title)
    return result, errors


def check_inputs_unchanged(run_id: str) -> None:
    lock = read_json(run_dir(run_id) / "inputs.lock.json", {})
    changed = [name for name, digest in lock.get("prompts", {}).items()
               if (ROOT / name).exists() and sha256_file(ROOT / name) != digest]
    if changed:
        log(f"warning: prompts changed since prepare ({', '.join(changed)}); "
            f"scores may not be comparable with earlier iterations")


def tool_version(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, timeout=60).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"


def trajviz_stage(out_dir: Path, label: str, ws: Path, title: str) -> None:
    """TrajViz export (+ views and HTML report when TrajViz is installed) of one agent run."""
    traj = out_dir / f"{label}.jsonl"
    if not traj.exists() or not traj.stat().st_size:
        return
    try:
        st = trajviz_export.export(CFG, traj, ws, out_dir / "transcripts" / label,
                                   out_dir / "trajviz", label, title)
    except Exception as e:  # analysis output must never break the loop
        log(f"  trajviz export failed for {out_dir.name}/{label}: {e}")
        return
    for err in st["errors"]:
        log(f"  trajviz: {err}")


def missing_deliverables(ws: Path) -> list[str]:
    """What an oracle or student workspace still lacks against the task's completion criteria."""
    os_root = ws / "openspec"
    name = CFG["change_name"]
    change = os_root / "changes" / name
    pre = set(CFG.get("preexisting_specs", []))
    missing = []
    if not any(p.parent.name not in pre for p in (os_root / "specs").glob("*/spec.md")):
        missing.append("baseline specs: openspec/specs/<capability-id>/spec.md")
    missing += [f"openspec/changes/{name}/{f}" for f in ("proposal.md", "design.md", "tasks.md")
                if not (change / f).exists()]
    if not any((change / "specs").glob("*/spec.md")):
        missing.append(f"delta specs: openspec/changes/{name}/specs/<capability-id>/spec.md")
    if not missing:
        v = guards.validate(ws)
        if not v["ok"]:
            issues = [f"{f['id']}: {i}" for f in v.get("failed", []) for i in f["issues"][:2]]
            missing.append("`openspec validate --all --strict` fails: " +
                           ("; ".join(issues[:5]) or str(v.get("error", ""))[:300]))
    return missing


def spec_run(state: dict, role: str, ws: Path, prompt_text: str, out_dir: Path, label: str,
             resume_session: str | None = None) -> dict:
    return run_agent(model=model_for(state, role), ws=ws, prompt=prompt_text, out_dir=out_dir,
                     label=label, timeout_min=timeout_for(state, role), resume_session=resume_session,
                     completion_check=lambda: missing_deliverables(ws),
                     max_nudges=CFG.get("completion_nudges", 0))


def run_labels(out_dir: Path) -> list[str]:
    return sorted(p.name.removesuffix(".run.json") for p in out_dir.glob("*.run.json"))


def finish_io_stage(run_id: str, ws: Path, out_dir: Path, outputs: tuple[str, ...], title: str) -> None:
    """For judge and synthesizer stages: copy the agent's _outputs/ files, render its trajectory,
    export every run for TrajViz and record that it wrote only under _outputs/."""
    for name in outputs:
        if (ws / "_outputs" / name).exists():
            shutil.copy2(ws / "_outputs" / name, out_dir / name)
    render_traj.render(out_dir / "trajectory.jsonl", ws, out_dir / "trajectory.md",
                       out_dir / "stats.json", CFG, out_dir / "transcripts" / "trajectory", title=title)
    for label in run_labels(out_dir):
        trajviz_stage(out_dir, label, ws, f"{run_id} {title} ({label})")
    write_json(out_dir / "guards.json", {"no_code": guards.no_code(ws, ("_outputs/",))})
    # _inputs/ holds the reference and other agents' specs; a student searching the disk must not
    # find them in a finished workspace (the copies under runs/ stay).
    remove_tree(ws / "_inputs")


def post_spec_stage(run_id: str, ws: Path, out_dir: Path, labels: list[str], title: str) -> dict:
    """Copy openspec/ out of the workspace, run guards, render trajectories, compute metrics."""
    spec_root = out_dir / "spec"
    copy_tree(ws / "openspec", spec_root / "openspec")
    transcripts = out_dir / "transcripts"
    result = {
        "no_code": guards.no_code(ws, ("openspec/",)),
        "validate": guards.validate(spec_root),
        "leak": {"ok": True, "violations": [], "warnings": []},
    }
    for label in labels:
        meta = read_json(out_dir / f"{label}.run.json", {})
        leak = guards.leak_check(CFG, ws, out_dir / f"{label}.jsonl", transcripts / label,
                                 meta.get("transcript_project"), ROOT)
        result["leak"]["ok"] &= leak["ok"]
        result["leak"]["violations"] += leak["violations"]
        result["leak"]["warnings"] += leak["warnings"]
        suffix = "" if label == "trajectory" else f".{label}"
        render_traj.render(out_dir / f"{label}.jsonl", ws, out_dir / f"trajectory{suffix}.md",
                           out_dir / f"stats{suffix}.json", CFG, transcripts / label,
                           title=f"{title} ({label})")
        trajviz_stage(out_dir, label, ws, f"{run_id} {title} ({label})")
    write_json(out_dir / "guards.json", result)
    metrics = spec_metrics.collect(spec_root, base_dir(run_id), CFG, hmos_index(run_id))
    write_json(out_dir / "metrics.json", metrics)
    log(f"guards: only-openspec={result['no_code']['ok']} validate={result['validate']['ok']} "
        f"leak-free={result['leak']['ok']}; baseline capabilities="
        f"{metrics['baseline_totals']['capabilities']}, change exists={metrics['change_exists']}")
    for v in result["leak"]["violations"][:5]:
        log(f"  LEAK {v['tool']} {v['path']} ({v['reason']})")
    for p in result["no_code"]["violations"][:5]:
        log(f"  wrote outside openspec/: {p}")
    return result


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict]) -> None:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_FIELDS)
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in CSV_FIELDS})
    path.write_text(buf.getvalue(), encoding="utf-8")


# ---------------------------------------------------------------- prepare / oracle / freeze

def cmd_prepare(args) -> None:
    rd = run_dir(args.run)
    if (rd / "state.json").exists() and not args.force:
        die(f"run '{args.run}' already exists (use --force to re-prepare)")
    src = getattr(args, "reference_from", None)
    if src:
        src_state = load_state(src)
        verify_frozen(src, src_state)
        if not src_state.get("reference_decisions", {}).get("frozen"):
            die(f"run '{src}' has no frozen reference decisions; freeze them first")
        src_sha = read_json(run_dir(src) / "inputs.lock.json", {}).get("base_sha")
        if src_sha != CFG["base_sha"]:
            die(f"run '{src}' was prepared at base {src_sha}, config.json has {CFG['base_sha']}; "
                f"its reference does not apply to this base")
    rd.mkdir(parents=True, exist_ok=True)
    remove_tree(base_dir(args.run))
    workspace.extract(CFG, base_dir(args.run))
    repo, sha = CFG["repo"], CFG["base_sha"]

    skills = {p.parent.name: sha256_file(p)
              for p in sorted(Path(CFG["cursor_dir"]).glob("skills/openspec-*/SKILL.md"))}
    prompt_files = ["rubric.md", "decision_vocab.json",
                    *[f"prompts/{p.name}" for p in sorted(PROMPTS.glob("*.md"))]]
    lock = {
        "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "base_sha": sha,
        "files": {p: sha256_bytes(git(repo, "show", f"{sha}:{p}"))
                  for p in ("AGENTS.md", "openspec/config.yaml")},
        "hmos_tree": git(repo, "rev-parse", f"{sha}:{CFG['hmos_dir']}").decode().strip(),
        "skills": skills,
        "prompts": {p: sha256_file(ROOT / p) for p in prompt_files},
        "config": sha256_file(ROOT / "config.json"),
        "models": {"smoke": CFG["smoke_model"]} if args.smoke else CFG["models"],
        "agent_cli": tool_version(["agent", "--version"]),
        "openspec_cli": tool_version(["openspec", "--version"]),
        "smoke": bool(args.smoke),
    }
    if (rd / "hmos_index.json").exists():
        (rd / "hmos_index.json").unlink()
    hmos_index(args.run)
    state = {"run": args.run, "smoke": bool(args.smoke), "naming": "sN",
             "oracle": {"status": "pending"}, "frozen": False, "iters": {}}
    if src:
        od, sd = oracle_dir(args.run), oracle_dir(src)
        remove_tree(od)
        copy_tree(sd / "spec", od / "spec")
        make_readonly(od / "spec")
        for name in ("MANIFEST.sha256", DECISIONS_FILE, "guards.json", "metrics.json"):
            if (sd / name).exists():
                shutil.copy2(sd / name, od / name)
        make_readonly(od / DECISIONS_FILE)
        src_state = load_state(src)
        state.update(frozen=True, frozen_at=src_state.get("frozen_at"),
                     reference_decisions={**src_state["reference_decisions"], "copied_from": src})
        state["oracle"] = {"status": "frozen", "reference_from": src,
                           "validate_ok": src_state["oracle"].get("validate_ok")}
        lock["reference_from"] = {"run": src, "manifest_sha256": sha256_file(od / "MANIFEST.sha256"),
                                  "decisions_sha256": sha256_file(od / DECISIONS_FILE)}
    write_json(rd / "inputs.lock.json", lock)
    save_state(args.run, state)
    if src:
        verify_frozen(args.run, state)
    log(f"prepared run '{args.run}' at {rd} (base {sha[:12]}{', smoke' if args.smoke else ''}"
        f"{f', frozen reference and decisions from {src}' if src else ''})")


def cmd_oracle(args) -> None:
    state = load_state(args.run)
    if state.get("frozen"):
        die("the oracle spec is frozen; it cannot be regenerated or revised")
    od = oracle_dir(args.run)
    ostate = state["oracle"]
    feedback = args.revise
    if args.revise_file:
        feedback = Path(args.revise_file).read_text(encoding="utf-8")

    if feedback is None:
        ws = workspace.build(CFG, args.run, "oracle")
        labels = ["trajectory"]
        meta = spec_run(state, "oracle", ws, task_text(state), od, "trajectory")
    else:
        if ostate.get("status") in (None, "pending") or not ostate.get("session_id"):
            die("there is no oracle session to revise; run `loop.py oracle` first")
        ws = Path(ostate["workspace"])
        copy = oracle_spec(args.run) / "openspec"
        if copy.exists() and manifest_text(copy) != manifest_text(ws / "openspec"):
            log("syncing reviewer edits from runs/.../oracle/spec into the oracle workspace")
            copy_tree(copy, ws / "openspec")
        labels = ostate.get("labels", ["trajectory"])
        label = f"revise{sum(1 for x in labels if x.startswith('revise')) + 1}"
        labels = [*labels, label]
        meta = spec_run(state, "oracle", ws, REVISE_PROMPT.format(feedback=feedback.strip()), od,
                        label, resume_session=ostate["session_id"])

    result = post_spec_stage(args.run, ws, od, labels, "oracle")
    fatal = []
    if not meta["ok"]:
        fatal.append("the agent run did not finish cleanly (see the .run.json)")
    if meta["incomplete"]:
        fatal.append("deliverables missing after nudges: " + "; ".join(meta["incomplete"]))
    if not result["no_code"]["ok"]:
        fatal.append("files were written outside openspec/")
    if not result["leak"]["ok"]:
        fatal.append("the trajectory touched forbidden paths")
    state = load_state(args.run)
    state["oracle"] = {
        "status": "failed" if fatal else "awaiting-review",
        "problems": fatal,
        "session_id": meta.get("session_id") or ostate.get("session_id"),
        "workspace": str(ws),
        "labels": labels,
        "validate_ok": result["validate"]["ok"],
    }
    save_state(args.run, state)
    if fatal:
        log("oracle run FAILED: " + "; ".join(fatal))
    else:
        log(f"oracle spec ready for review: {oracle_spec(args.run) / 'openspec'}")
        if not result["validate"]["ok"]:
            log("note: `openspec validate --all --strict` fails; see oracle/guards.json")
        log("next: edit the spec directly and/or `loop.py oracle --revise ...`, then `loop.py freeze`")


def freeze_reference_decisions(run_id: str, state: dict) -> None:
    """Freeze oracle/decisions.proposed.json (as reviewed by the human) into oracle/decisions.json."""
    proposed = oracle_dir(run_id) / "decisions.proposed.json"
    if not proposed.exists():
        log(f"the reference decisions are not extracted yet: run `loop.py extract --run {run_id} --target "
            f"oracle`, review oracle/decisions.review.md, then `loop.py freeze --run {run_id}` again "
            f"(compare needs them)")
        return
    vocab = dec.load_vocab()
    clean, report = dec.validate_extraction(dec.to_raw(read_json(proposed)), vocab,
                                            dec.spec_corpus(oracle_spec(run_id), CFG), hmos_index(run_id),
                                            base_dir(run_id), CFG["hmos_dir"])
    if report["errors"]:
        die("oracle/decisions.proposed.json does not validate:\n" +
            "\n".join(f"- {e}" for e in report["errors"]))
    dst = oracle_dir(run_id) / DECISIONS_FILE
    if dst.exists():
        make_writable(dst)
    write_json(dst, clean)
    make_readonly(dst)
    state["reference_decisions"] = {
        "frozen": True, "frozen_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "sha256": sha256_file(dst),
        "stated": sum(1 for k in dec.KINDS for e in clean[k].values() if e.get("value"))}
    save_state(run_id, state)
    (oracle_dir(run_id) / "MANIFEST.sha256").write_text(manifest_expected(run_id, state), encoding="utf-8")
    log(f"reference decisions frozen ({state['reference_decisions']['stated']} stated): {dst}")


def cmd_freeze(args) -> None:
    state = load_state(args.run)
    if state.get("frozen"):
        verify_frozen(args.run, state)
        if state.get("reference_decisions", {}).get("frozen"):
            log("already frozen (spec and reference decisions)")
        else:
            freeze_reference_decisions(args.run, state)
        return
    if state["oracle"].get("status") != "awaiting-review" and not args.force:
        die(f"oracle status is '{state['oracle'].get('status')}'; only a reviewed spec can be frozen "
            f"(use --force to override)")
    spec_root = oracle_spec(args.run)
    v = guards.validate(spec_root)
    if not v["ok"] and not args.force:
        die("`openspec validate --all --strict` fails on the oracle spec:\n" +
            json.dumps(v.get("failed") or v.get("error"), ensure_ascii=False, indent=2) +
            "\nfix it (edit or --revise) or pass --force")
    metrics = spec_metrics.collect(spec_root, base_dir(args.run), CFG, hmos_index(args.run))
    write_json(oracle_dir(args.run) / "metrics.json", metrics)
    guards_path = oracle_dir(args.run) / "guards.json"
    g = read_json(guards_path, {})
    g["validate"] = v
    write_json(guards_path, g)
    (oracle_dir(args.run) / "MANIFEST.sha256").write_text(manifest_text(spec_root), encoding="utf-8")
    make_readonly(spec_root)
    state["frozen"] = True
    state["frozen_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    state["oracle"]["status"] = "frozen"
    save_state(args.run, state)
    log(f"oracle spec frozen ({sum(1 for p in spec_root.rglob('*') if p.is_file())} files); "
        f"manifest at {oracle_dir(args.run) / 'MANIFEST.sha256'}")
    freeze_reference_decisions(args.run, state)


def cmd_extract(args) -> None:
    """Extract a decision table from a spec (a run-relative directory holding spec/) or a playbook
    (a run-relative .md file), in N parallel passes. For --target oracle this proposes the
    reference decisions for human review."""
    state = load_state(args.run)
    rd = run_dir(args.run)
    target = rd / args.target
    is_playbook = target.suffix == ".md"
    if is_playbook and not target.exists():
        die(f"no playbook at {target}")
    if not is_playbook and not (target / "spec" / "openspec").is_dir():
        die(f"no spec at {target / 'spec' / 'openspec'}")
    if args.target == "oracle" and state.get("reference_decisions", {}).get("frozen"):
        log("note: the reference decisions are already frozen; this only writes a new proposal")
    out_root = rd / args.out if args.out else (target.parent / "decisions" if is_playbook
                                               else target / "decisions")
    slug = args.target.strip("/").replace("/", "-").removesuffix(".md")

    def one(p: int):
        out, stage, title = out_root / f"pass-{p}", f"extract-{slug}-p{p}", f"extract {args.target} pass {p}"
        if is_playbook:
            return extract_playbook(args.run, state, target, out, stage, title)
        return extract_spec(args.run, state, target / "spec", out, stage, title)

    passes = max(1, args.passes)
    with ThreadPoolExecutor(max_workers=passes) as pool:
        tables = list(pool.map(one, range(1, passes + 1)))
    ok = [t for t in tables if t is not None]
    if not ok:
        die("every extraction pass failed")
    vocab = dec.load_vocab()
    ag = None
    if len(ok) >= 2:
        ag = dec.extraction_agreement(ok[0], ok[1], vocab)
        write_json(out_root / "agreement.json", ag)
        log(f"passes agree on {ag['agreement']:.1%} of {ag['items']} keys "
            f"({ag['stated_agreement']:.1%} of the {ag['stated_items']} keys at least one pass states)")
        for d in ag["diffs"]:
            log(f"  differs: {d['id']}: {d['a']} vs {d['b']}")
    if args.target == "oracle":
        write_json(oracle_dir(args.run) / "decisions.proposed.json", ok[0])
        mod = dec.module_table(oracle_spec(args.run), hmos_index(args.run), CFG)
        (oracle_dir(args.run) / "decisions.review.md").write_text(
            dec.render_review(ok[0], mod, vocab, ag, ok[1] if len(ok) >= 2 else None), encoding="utf-8")
        log(f"proposed reference decisions: {oracle_dir(args.run) / 'decisions.proposed.json'}; review "
            f"{oracle_dir(args.run) / 'decisions.review.md'}, then `loop.py freeze --run {args.run}`")


# ---------------------------------------------------------------- student

def sample_label(state: dict, sample: int, samples: int) -> str:
    """Directory suffix of a sample: runs prepared since the `-sN` naming always use `-sN`; older
    runs (r1) used no suffix for a single sample."""
    return f"-s{sample}" if state.get("naming") == "sN" or samples > 1 else ""


def iteration_samples(run_id: str, k: int) -> list[tuple[str, Path, Path]]:
    """(label, student dir, compare dir) of every sample of an iteration; a plain `student`
    directory (r1) reads as s1."""
    it = iter_dir(run_id, k)
    out = []
    for d in sorted(it.glob("student*"), key=lambda p: (len(p.name), p.name)):
        sfx = d.name[len("student"):]
        if d.is_dir() and (sfx == "" or re.fullmatch(r"-s\d+", sfx)):
            out.append((sfx[1:] if sfx else "s1", d, it / f"compare{sfx}"))
    return out


def playbook_prompt(state: dict, playbook: str | None) -> str:
    text = task_text(state)
    if playbook is None:
        return text
    return (text.rstrip() + "\n\n---\n\n# Playbook\n\n"
            "The playbook below comes from earlier attempts at this same task. Follow it.\n\n" +
            playbook.strip() + "\n")


def student_prompt(state: dict, run_id: str, k: int) -> str:
    if k == 0:
        return playbook_prompt(state, None)
    pb = iter_dir(run_id, k - 1) / "playbook" / "playbook.md"
    if not pb.exists():
        die(f"iteration {k} needs the playbook from iteration {k - 1}: {pb} is missing")
    return playbook_prompt(state, pb.read_text(encoding="utf-8"))


def run_student(run_id: str, state: dict, out_dir: Path, stage: str, text: str, title: str,
                label: str) -> dict:
    """One student run in a fresh workspace, retried from scratch while it is invalid."""
    attempts = CFG.get("student_retries", 0) + 1
    for attempt in range(1, attempts + 1):
        ws = workspace.build(CFG, run_id, stage)
        meta = spec_run(state, "student", ws, text, out_dir, "trajectory")
        result = post_spec_stage(run_id, ws, out_dir, ["trajectory"], title)
        valid = meta["ok"] and result["leak"]["ok"] and not meta["incomplete"]
        if valid or attempt == attempts:
            break
        log(f"{title}: invalid run (agent ok={meta['ok']}, leak-free={result['leak']['ok']}, "
            f"missing={meta['incomplete']}); retrying ({attempt}/{attempts - 1})")
    return {"sample": label or "-", "valid": valid, "agent_ok": meta["ok"],
            "leak_ok": result["leak"]["ok"], "no_code_ok": result["no_code"]["ok"],
            "validate_ok": result["validate"]["ok"], "nudges": meta["nudges"],
            "incomplete": meta["incomplete"], "session_id": meta.get("session_id"),
            "workspace": str(ws), "attempts": attempt}


def run_student_sample(run_id: str, state: dict, k: int, sample: int, samples: int,
                       text: str) -> dict:
    sfx = sample_label(state, sample, samples)
    return run_student(run_id, state, iter_dir(run_id, k) / f"student{sfx}", f"iter-{k:02d}-student{sfx}",
                       text, f"student iter {k}{sfx}", sfx)


def cmd_student(args) -> None:
    state = load_state(args.run)
    k = args.iter
    if k > 0 or state.get("frozen"):
        verify_frozen(args.run, state)
    check_inputs_unchanged(args.run)
    text = student_prompt(state, args.run, k)
    if args.dry_run:
        print(text)
        log(f"prompt: {len(text.encode('utf-8'))} bytes")
        return
    samples = max(1, args.samples)
    with ThreadPoolExecutor(max_workers=samples) as pool:
        futures = [pool.submit(run_student_sample, args.run, state, k, s, samples, text)
                   for s in range(1, samples + 1)]
        results = [f.result() for f in futures]
    state = load_state(args.run)
    it = state["iters"].setdefault(str(k), {})
    it["samples"] = samples
    it["student"] = results
    save_state(args.run, state)
    for r in results:
        log(f"student iter {k} sample {r['sample']}: valid={r['valid']} validate={r['validate_ok']} "
            f"only-openspec={r['no_code_ok']}")


# ---------------------------------------------------------------- compare

def extract_decisions(run_id: str, state: dict, stage: str, out_dir: Path, inputs: dict[str, Path],
                      prompt_name: str, corpus: dict[str, str], require_all: bool, title: str) -> dict | None:
    """Run the extractor; write decisions.raw.json, decisions.json (validated) and validation.json."""
    index, vocab = hmos_index(run_id), dec.load_vocab()
    out_dir.mkdir(parents=True, exist_ok=True)
    ws = workspace.build(CFG, run_id, stage, {**inputs, "decision_vocab.json": dec.VOCAB_PATH})
    report: dict = {}

    def check(raw):
        write_json(out_dir / "decisions.raw.json", raw)
        clean, rep = dec.validate_extraction(copy.deepcopy(raw), vocab, corpus, index, base_dir(run_id),
                                             CFG["hmos_dir"], require_all)
        report.clear()
        report.update(rep)
        return clean, rep["errors"]
    table, errors = run_checked_agent(state, "extractor", run_id, ws,
                                      prompt(prompt_name, change_name=CFG["change_name"]), out_dir,
                                      "decisions.json", check, CFG.get("extract_fix_retries", 0), title, ())
    if table is None:
        write_json(out_dir / "validation.json", {"errors": errors})
        log(f"{title} FAILED: " + "; ".join(errors[:5]))
        return None
    write_json(out_dir / "decisions.json", table)
    write_json(out_dir / "validation.json", report)
    stated = sum(1 for k in dec.KINDS for e in table[k].values() if e.get("value"))
    log(f"{title}: {stated} decisions stated, {len(report.get('dropped', []))} dropped as invalid, "
        f"{len(report.get('warnings', []))} warnings")
    return table


def extract_spec(run_id: str, state: dict, spec_root: Path, out_dir: Path, stage: str,
                 title: str) -> dict | None:
    return extract_decisions(run_id, state, stage, out_dir, {"spec": spec_root}, "extract.md",
                             dec.spec_corpus(spec_root, CFG), True, title)


def extract_playbook(run_id: str, state: dict, playbook: Path, out_dir: Path, stage: str,
                     title: str) -> dict | None:
    text = playbook.read_text(encoding="utf-8", errors="replace")
    out_dir.mkdir(parents=True, exist_ok=True)
    task = out_dir / "_task.md"
    task.write_text(task_text(state), encoding="utf-8")
    table = extract_decisions(run_id, state, stage, out_dir, {"playbook.md": playbook, "task.md": task},
                              "extract_playbook.md", {"playbook.md": text}, False, title)
    task.unlink(missing_ok=True)
    return table


def run_disputes(run_id: str, state: dict, stage: str, out_dir: Path, disputes: list[dict],
                 stu_spec: Path, title: str) -> dict | None:
    """One ruling per disagreement; entries the judge leaves out count as student_wrong."""
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out_dir / "_staging"
    tmp.mkdir(exist_ok=True)
    write_json(tmp / "disputes.json", disputes)
    (tmp / "task.md").write_text(task_text(state), encoding="utf-8")
    ws = workspace.build(CFG, run_id, stage, {"disputes.json": tmp / "disputes.json", "task.md": tmp / "task.md",
                                              "reference": oracle_spec(run_id), "student": stu_spec})
    ids = [d["id"] for d in disputes]
    rulings, errors = run_checked_agent(state, "judge", run_id, ws, prompt("disputes.md", change_name=CFG["change_name"]),
                                        out_dir, "rulings.json", lambda raw: dec.validate_rulings(raw, ids),
                                        CFG.get("judge_fix_retries", 0), title, ("rulings.json",))
    shutil.rmtree(tmp, ignore_errors=True)
    if not rulings:
        log(f"{title} FAILED: " + "; ".join(errors[:5]))
        return None
    for i in ids:
        rulings.setdefault(i, {"ruling": "student_wrong", "severity": "medium",
                               "reason": "裁定缺失，按 student_wrong 计", "evidence": "-"})
    write_json(out_dir / "rulings.checked.json", {"rulings": rulings, "errors": errors})
    return rulings


def check_soft(data) -> tuple[dict | None, list[str]]:
    errors = []
    if not isinstance(data, dict):
        return None, ["top level must be an object"]
    parts = data.get("parts")
    if not isinstance(parts, dict):
        errors.append("missing object 'parts'")
        parts = {}
    for key in SOFT_PARTS:
        entry = parts.get(key)
        if not isinstance(entry, dict):
            errors.append(f"parts.{key} is missing")
            continue
        s = entry.get("score")
        if not isinstance(s, int) or isinstance(s, bool) or not 0 <= s <= 5:
            errors.append(f"parts.{key}.score must be an integer 0-5 (got {s!r})")
    gaps = data.get("gaps")
    if not isinstance(gaps, list):
        errors.append("missing list 'gaps'")
        gaps = []
    dims = sorted(set(SOFT_PARTS.values()))
    for i, g in enumerate(gaps):
        if not isinstance(g, dict):
            errors.append(f"gaps[{i}] must be an object")
            continue
        for field in ("id", "summary"):
            if not isinstance(g.get(field), str) or not g.get(field):
                errors.append(f"gaps[{i}].{field} is missing")
        if g.get("dimension") not in dims:
            errors.append(f"gaps[{i}].dimension must be one of {dims}")
        if g.get("severity") not in SEVERITIES:
            errors.append(f"gaps[{i}].severity must be one of {sorted(SEVERITIES)}")
        if g.get("tag") not in TAGS:
            errors.append(f"gaps[{i}].tag must be one of {sorted(TAGS)}")
    return data, errors[:30]


def run_soft_judge(run_id: str, state: dict, stage: str, out_dir: Path, stu_dir: Path,
                   metrics_md: Path, code_checks_md: Path, prev_score: Path | None,
                   title: str) -> dict | None:
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out_dir / "_staging"
    tmp.mkdir(exist_ok=True)
    (tmp / "task.md").write_text(task_text(state), encoding="utf-8")
    inputs = {"task.md": tmp / "task.md", "rubric.md": ROOT / "rubric.md",
              "reference": oracle_spec(run_id), "student": stu_dir / "spec",
              "metrics.md": metrics_md, "code_checks.md": code_checks_md}
    if prev_score is not None and prev_score.exists():
        gaps = [{"id": g.get("id"), "summary": g.get("summary")}
                for g in (read_json(prev_score, {}) or {}).get("gaps", []) if g.get("source") == "judge"]
        write_json(tmp / "previous_gaps.json", gaps)
        inputs["previous_gaps.json"] = tmp / "previous_gaps.json"
    ws = workspace.build(CFG, run_id, stage, inputs)
    data, errors = run_checked_agent(state, "judge", run_id, ws, prompt("compare.md", change_name=CFG["change_name"]),
                                     out_dir, "soft_score.json", check_soft, CFG.get("judge_fix_retries", 0),
                                     title, ("soft_score.json", "soft_report.md"),
                                     also=" (and `_outputs/soft_report.md` if the scores change)")
    shutil.rmtree(tmp, ignore_errors=True)
    if errors:
        log(f"{title} FAILED: " + "; ".join(errors[:5]))
        return None
    return data


def render_code_checks(coverage: dict, behaviour: dict, grounding: float, tasks: dict, build: dict,
                       rules: dict) -> str:
    out = ["# Script checks of the student spec", "",
           "Computed by the script and scored without you. Do not score these again.", "",
           f"- HMOS module directories covered by a baseline capability: {coverage['value']:.2f}"
           f" (not covered: {', '.join(coverage['missing']) or 'none'})",
           f"- Behaviour coverage: the student's baseline specs cite {behaviour['recall']:.0%} of the "
           f"{behaviour['reference_names']} HMOS names the reference's baseline cites ({behaviour['student_names']} "
           f"names cited in total, padding factor {behaviour['padding_factor']}). Whether the requirements "
           f"around those names describe the behaviour correctly is yours to judge.",
           f"- Reference grounding (backticked names found in the HMOS tree): {grounding:.3f}",
           f"- tasks.md rules (gate per group, gtest per group, gni sync on deletions): {tasks['value']:.2f} "
           f"{json.dumps(tasks.get('parts', {}))}",
           f"- callmanager.gni / bundle.json coverage: {build['value']:.2f}",
           f"- Readability checklist: {rules['value']:.2f}"]
    out += [f"  - {k}: {c['value']} {c['detail']}" for k, c in rules["checks"].items()]
    return "\n".join(out) + "\n"


def shared_idents(run_id: str, state: dict) -> set[str]:
    base = base_dir(run_id)
    texts = [(base / rel).read_text(encoding="utf-8", errors="replace")
             for rel in ("AGENTS.md", "openspec/config.yaml") if (base / rel).exists()]
    return dec.allowed_symbols([*texts, task_text(state)])[0]


def reuse_json(path: Path, ok) -> dict | None:
    data = read_json(path) if path.exists() else None
    if data is not None and ok(data):
        log(f"reusing {path}")
        return data
    return None


def score_sample(run_id: str, state: dict, k: int, stage: str, stu_dir: Path, out_dir: Path,
                 ref_table: dict, stu_table: dict | None = None, prev_score: Path | None = None,
                 reuse: bool = False, judges: int = 1) -> dict | None:
    """Score one student spec: code checks, then (in parallel) extraction -> table diff -> disputes,
    and the soft judge; aggregate in code. Writes score.json, report.md and decisions_compare.json.
    With `judges` > 1, each judge pass (disputes + soft judge) is independent and kept in
    judge-M/; the sample's total is the mean of the passes' totals, gaps use majority rulings.
    With `reuse`, model outputs already in `out_dir` (extraction, rulings covering every dispute,
    soft score) are taken as they are, so a change to the scoring code needs no new agent runs."""
    if not (stu_dir / "spec").exists():
        die(f"no student spec at {stu_dir / 'spec'}")
    index, vocab = hmos_index(run_id), dec.load_vocab()
    ref_m = spec_metrics.collect(oracle_spec(run_id), base_dir(run_id), CFG, index)
    stu_m = read_json(stu_dir / "metrics.json") or \
        spec_metrics.collect(stu_dir / "spec", base_dir(run_id), CFG, index)
    d = spec_metrics.diff(ref_m, stu_m)
    out_dir.mkdir(parents=True, exist_ok=True)
    stu_guards = read_json(stu_dir / "guards.json", {})
    md = spec_metrics.render_md(ref_m, stu_m, d, read_json(oracle_dir(run_id) / "guards.json", {}), stu_guards)
    (out_dir / "metrics.md").write_text(md, encoding="utf-8")
    write_json(out_dir / "metrics_diff.json", d)

    ref_mod = dec.module_table(oracle_spec(run_id), index, CFG)
    stu_mod = dec.module_table(stu_dir / "spec", index, CFG)
    modules = dec.all_modules(index)
    missing = sorted(set(modules) - set(stu_mod["covered"]))
    coverage = {"value": round(1 - len(missing) / len(modules), 4), "missing": missing}
    grounding = stu_m.get("reference_grounding") or 0.0
    tasks = dec.task_rules(stu_dir / "spec", CFG)
    build = dec.build_coverage(oracle_spec(run_id), stu_dir / "spec", base_dir(run_id), CFG)
    rules = dec.rule_checklist(stu_dir / "spec", CFG, stu_guards.get("validate", {}).get("ok"), stu_mod)
    shared = shared_idents(run_id, state)
    behaviour = dec.behaviour_coverage(dec.cited_names(oracle_spec(run_id), CFG, index, shared),
                                       dec.cited_names(stu_dir / "spec", CFG, index, shared),
                                       SCORING["coverage_padding_ratio"])
    (out_dir / "code_checks.md").write_text(
        render_code_checks(coverage, behaviour, grounding, tasks, build, rules), encoding="utf-8")
    if reuse and stu_table is None:
        stu_table = reuse_json(out_dir / "decisions" / "decisions.json", lambda d: "features" in d)
    jdirs = [out_dir] if judges <= 1 else [out_dir / f"judge-{m}" for m in range(1, judges + 1)]
    jtag = (lambda m: "") if judges <= 1 else (lambda m: f"-j{m}")

    def soft_pass(m: int, jdir: Path):
        old = reuse_json(jdir / "soft" / "soft_score.json", lambda d: not check_soft(d)[1]) if reuse else None
        return old or run_soft_judge(run_id, state, f"{stage}-soft{jtag(m)}", jdir / "soft", stu_dir,
                                     out_dir / "metrics.md", out_dir / "code_checks.md", prev_score,
                                     f"soft judge {stage}{jtag(m)}")

    def dispute_pass(m: int, jdir: Path, disputes: list[dict]):
        if not disputes:
            return {}
        ids = {d["id"] for d in disputes}
        old = reuse_json(jdir / "disputes" / "rulings.checked.json",
                         lambda d: ids <= set(d.get("rulings", {}))) if reuse else None
        if old is not None:
            return {i: old["rulings"][i] for i in ids}
        return run_disputes(run_id, state, f"{stage}-disputes{jtag(m)}", jdir / "disputes", disputes,
                            stu_dir / "spec", f"disputes {stage}{jtag(m)}")

    with ThreadPoolExecutor(max_workers=2 * len(jdirs) + 1) as pool:
        f_table = pool.submit(lambda: stu_table if stu_table is not None else extract_spec(
            run_id, state, stu_dir / "spec", out_dir / "decisions", f"{stage}-extract",
            f"extract {stu_dir.relative_to(run_dir(run_id))}"))
        f_soft = [pool.submit(soft_pass, m, jd) for m, jd in enumerate(jdirs, 1)]
        table = f_table.result()
        items = disputes = None
        f_rul = []
        if table is not None:
            items = dec.compare(ref_table, table, ref_mod, stu_mod, vocab, index)
            disputes = dec.dispute_inputs(items, ref_table, table, ref_mod, stu_mod, vocab)
            log(f"{stage}: {len(items) - len(disputes)} of {len(items)} decisions agree; "
                f"{len(disputes)} to dispute")
            f_rul = [pool.submit(dispute_pass, m, jd, disputes) for m, jd in enumerate(jdirs, 1)]
        softs = [f.result() for f in f_soft]
        rulings_list = [f.result() for f in f_rul]
    if table is None or any(s is None for s in softs) or any(r is None for r in rulings_list):
        return None

    checks = {"module_coverage": coverage,
              "behaviour_coverage": {**behaviour, "missing": behaviour["missing"][:200]},
              "grounding_rate": grounding, "task_rules": tasks, "build_coverage": build, "rule_checklist": rules}
    code_parts = {"module_coverage": coverage["value"], "behaviour_coverage": behaviour["value"],
                  "grounding_rate": grounding, "task_rules": tasks["value"], "build_coverage": build["value"],
                  "rule_checklist": rules["value"]}
    code_gaps = dec.check_gaps(missing, behaviour, rules, tasks)

    def assemble(rulings: dict, soft_parts: dict[str, float], rationales: dict[str, str],
                 soft_gaps: list[dict]) -> dict:
        agree = dec.agreement(items, rulings)
        parts = {part: agree[group]["value"] for group, part in dec.GROUP_PART.items()}
        parts.update(code_parts)
        parts.update(soft_parts)
        dims, total = dec.aggregate(SCORING, parts)
        for p, dim in SOFT_PARTS.items():
            dims[dim]["rationale"] = rationales.get(p, "")
        return {"scoring": "decisions-v2", "total": total, "dimensions": dims, "weights": SCORING["weights"],
                "agreement": agree, "code_share": dec.code_share(SCORING, parts, agree),
                "disputes": len(disputes), "gaps": dec.decision_gaps(items, rulings, vocab) + code_gaps + soft_gaps,
                "code_checks": checks}

    def soft_report(jdir: Path) -> str:
        p = jdir / "soft" / "soft_report.md"
        return p.read_text(encoding="utf-8") if p.exists() else ""

    per_judge = [assemble(r, {p: s["parts"][p]["score"] / 5 for p in SOFT_PARTS},
                          {p: s["parts"][p].get("rationale", "") for p in SOFT_PARTS},
                          [{**g, "source": "judge"} for g in s.get("gaps", [])])
                 for r, s in zip(rulings_list, softs)]
    if judges <= 1:
        score, rulings, report_soft = per_judge[0], rulings_list[0], soft_report(out_dir)
    else:
        for m, (jd, sc) in enumerate(zip(jdirs, per_judge), 1):
            write_json(jd / "score.json", sc)
            (jd / "report.md").write_text(dec.render_report(sc, items, rulings_list[m - 1], coverage, behaviour,
                                                            rules, tasks, build, soft_report(jd), vocab),
                                          encoding="utf-8")
        rulings = dec.majority_rulings(rulings_list)
        soft_gaps, seen = [], set()
        for m, s in enumerate(softs, 1):
            for g in s.get("gaps", []):
                if g.get("id") not in seen:
                    seen.add(g.get("id"))
                    soft_gaps.append({**g, "source": "judge", "judge": m})
        score = assemble(rulings, {p: statistics.mean(s["parts"][p]["score"] for s in softs) / 5 for p in SOFT_PARTS},
                         {p: " | ".join(f"J{m}: {s['parts'][p].get('rationale', '')}" for m, s in enumerate(softs, 1))
                          for p in SOFT_PARTS}, soft_gaps)
        totals = [sc["total"] for sc in per_judge]
        score["total"] = round(statistics.mean(totals), 1)
        for dim in DIMENSIONS:
            v = statistics.mean(sc["dimensions"][dim]["value"] for sc in per_judge)
            score["dimensions"][dim].update(value=round(v, 4), score=round(v * 5, 2))
        score["judges"] = [{"judge": m, "total": sc["total"],
                            "dimensions": {d: sc["dimensions"][d]["value"] for d in DIMENSIONS},
                            "soft_parts": {p: s["parts"][p]["score"] for p in SOFT_PARTS}}
                           for m, (sc, s) in enumerate(zip(per_judge, softs), 1)]
        score["judge_spread"] = round(max(totals) - min(totals), 1)
        report_soft = "\n\n".join(f"### 评审 {m}\n\n{soft_report(jd)}" for m, jd in enumerate(jdirs, 1))
    write_json(out_dir / "score.json", score)
    write_json(out_dir / "decisions_compare.json", {
        "items": items, "rulings": rulings, "student_decisions": table,
        **({"rulings_by_judge": rulings_list} if judges > 1 else {}),
        "modules": {"reference": ref_mod, "student": stu_mod}})
    (out_dir / "report.md").write_text(dec.render_report(score, items, rulings, coverage, behaviour, rules,
                                                         tasks, build, report_soft, vocab), encoding="utf-8")
    summary = ", ".join(f"{key} {score['dimensions'][key]['score']}" for key in DIMENSIONS)
    judged = f" (judges {', '.join(str(j['total']) for j in score['judges'])})" if judges > 1 else ""
    log(f"{stage}: total {score['total']}{judged} ({summary}); "
        f"code share {score['code_share']['code_share_of_total']:.0%}")
    return score


def score_row(k: int, label: str, data: dict, stu_dir: Path) -> dict:
    stu_guards = read_json(stu_dir / "guards.json", {})
    stu_stats = read_json(stu_dir / "stats.json", {})
    usage = stu_stats.get("usage", {})
    return {"iter": k, "sample": label or "-", "total": data["total"],
            **{key: data["dimensions"][key]["score"] for key in DIMENSIONS},
            "judges": len(data.get("judges", [])) or 1, "judge_spread": data.get("judge_spread", ""),
            "code_share": data["code_share"]["code_share_of_total"], "disputes": data["disputes"],
            "gaps_student_wrong": sum(1 for g in data["gaps"] if g["tag"] == "student_wrong"),
            "gaps_high": sum(1 for g in data["gaps"]
                             if g["tag"] == "student_wrong" and g["severity"] == "high"),
            "validate_ok": stu_guards.get("validate", {}).get("ok"),
            "leak_ok": stu_guards.get("leak", {}).get("ok"),
            "no_code_ok": stu_guards.get("no_code", {}).get("ok"),
            "hmos_coverage": stu_stats.get("hmos_coverage"),
            "subagents": stu_stats.get("subagents"),
            "nudges": read_json(stu_dir / "trajectory.run.json", {}).get("nudges", 0),
            "input_tokens": usage.get("inputTokens"), "output_tokens": usage.get("outputTokens"),
            "duration_min": round((stu_stats.get("duration_ms") or 0) / 60000, 1),
            "model": stu_stats.get("model_reported")}


def run_compare_sample(run_id: str, state: dict, k: int, sample: int, samples: int, judges: int) -> dict:
    sfx = sample_label(state, sample, samples)
    it_dir = iter_dir(run_id, k)
    stu_dir = it_dir / f"student{sfx}"
    out_dir = it_dir / f"compare{sfx}"
    if not (stu_dir / "spec").exists():
        die(f"no student spec for iteration {k}{sfx}; run `loop.py student --iter {k}` first")
    prev = None
    if k > 0:
        earlier = {label: c for label, _s, c in iteration_samples(run_id, k - 1)}
        prev = (earlier.get(sfx[1:] if sfx else "s1") or next(iter(earlier.values()), it_dir)) / "score.json"
    data = score_sample(run_id, state, k, f"iter-{k:02d}-compare{sfx}", stu_dir, out_dir,
                        reference_decisions(run_id, state), prev_score=prev, judges=judges)
    if data is None:
        log(f"compare iter {k}{sfx} FAILED; see {out_dir}")
        return {"sample": sfx or "-", "ok": False}
    row = score_row(k, sfx, data, stu_dir)
    csv_path = run_dir(run_id) / "scores.csv"
    rows = [r for r in read_csv(csv_path) if not (r["iter"] == str(k) and r["sample"] == row["sample"])]
    rows.append(row)
    rows.sort(key=lambda r: (int(r["iter"]), r["sample"]))
    write_csv(csv_path, rows)
    return {"sample": sfx or "-", "ok": True, "total": data["total"],
            "judge_totals": [j["total"] for j in data.get("judges", [])]}


def iteration_scores(state: dict) -> dict[int, float]:
    return {int(j): v["score"] for j, v in state["iters"].items() if v.get("score") is not None}


def change_vs_best(state: dict, k: int) -> dict | None:
    """Iteration k's score against the best earlier iteration, marked against the noise threshold."""
    scores = iteration_scores(state)
    earlier = {j: s for j, s in scores.items() if j < k}
    if k not in scores or not earlier:
        return None
    best = max(earlier, key=lambda j: (earlier[j], j))
    delta = round(scores[k] - earlier[best], 1)
    threshold = state.get("noise", {}).get("threshold")
    mark = "" if threshold is None else "significant" if abs(delta) > threshold else "within noise"
    return {"delta": delta, "best_iter": best, "best": earlier[best], "threshold": threshold, "mark": mark}


def stable_gap_ids(score: dict) -> set[str]:
    """student_wrong gaps whose ids come from code (decision items, coverage, rules), not the judge."""
    return {g["id"] for g in score.get("gaps", [])
            if g.get("tag") == "student_wrong" and g.get("source") in ("decision", "code")}


def majority_gaps(scores: list[dict]) -> set[str]:
    counts: dict[str, int] = {}
    for s in scores:
        for i in stable_gap_ids(s):
            counts[i] = counts.get(i, 0) + 1
    return {i for i, n in counts.items() if n * 2 >= len(scores)}


def iteration_gaps(run_id: str, k: int) -> set[str] | None:
    scores = [read_json(c / "score.json") for _l, _s, c in iteration_samples(run_id, k)
              if (c / "score.json").exists()]
    return majority_gaps(scores) if scores else None


def mark_iteration(run_id: str, state: dict, k: int) -> None:
    """Fill vs_best, gaps_closed and gaps_reopened in the scores.csv rows of iteration k."""
    change = change_vs_best(state, k)
    prev = iteration_gaps(run_id, k - 1) if k > 0 else None
    earlier: set[str] = set()
    for j in range(k - 1):
        earlier |= iteration_gaps(run_id, j) or set()
    csv_path = run_dir(run_id) / "scores.csv"
    rows = read_csv(csv_path)
    samples = {label: c for label, _s, c in iteration_samples(run_id, k)}
    for r in rows:
        if r["iter"] != str(k):
            continue
        if change:
            r["vs_best"] = f"{change['delta']:+.1f}" + (f" {change['mark']}" if change["mark"] else "")
        cmp_dir = samples.get(r["sample"].lstrip("-") if r["sample"] != "-" else "s1")
        ids = stable_gap_ids(read_json(cmp_dir / "score.json", {})) if cmp_dir else set()
        if prev is not None:
            r["gaps_closed"] = len(prev - ids)
            r["gaps_reopened"] = len((ids - prev) & earlier)
    write_csv(csv_path, rows)
    if change:
        log(f"iteration {k}: score {iteration_scores(state)[k]}, {change['delta']:+.1f} vs the best earlier "
            f"iteration {change['best_iter']} ({change['best']})"
            + (f": {change['mark']} (threshold {change['threshold']})" if change["mark"] else
               " (no noise threshold measured yet)"))


def cmd_compare(args) -> None:
    state = load_state(args.run)
    verify_frozen(args.run, state)
    check_inputs_unchanged(args.run)
    k = args.iter
    judges = args.judges or CFG.get("judges", 1)
    samples = state["iters"].get(str(k), {}).get("samples", 1)
    with ThreadPoolExecutor(max_workers=samples) as pool:
        results = [f.result() for f in [pool.submit(run_compare_sample, args.run, state, k, s, samples, judges)
                                        for s in range(1, samples + 1)]]
    state = load_state(args.run)
    it = state["iters"].setdefault(str(k), {})
    it["compare"] = results
    it["judges"] = judges
    totals = [r["total"] for r in results if r.get("ok")]
    it["score"] = round(statistics.mean(totals), 1) if totals else None
    it["vs_best"] = change_vs_best(state, k)
    save_state(args.run, state)
    mark_iteration(args.run, state, k)


def cmd_rescore(args) -> None:
    """Score an existing student spec with the current scoring into iter-KK/<out>/; touches
    neither state.json nor scores.csv."""
    state = load_state(args.run)
    verify_frozen(args.run, state)
    rd = run_dir(args.run)
    samples = iteration_samples(args.run, args.iter)
    if not args.student and not samples:
        die(f"iteration {args.iter} has no student sample")
    stu_dir = rd / args.student if args.student else samples[0][1]
    out_dir = iter_dir(args.run, args.iter) / args.out
    stu_table = None
    if args.student_decisions:
        stu_table = read_json(rd / args.student_decisions)
        log(f"reusing the student decision table {args.student_decisions}")
    score = score_sample(args.run, state, args.iter, f"iter-{args.iter:02d}-{args.out}", stu_dir, out_dir,
                         reference_decisions(args.run, state, allow_proposed=True), stu_table,
                         reuse=args.reuse, judges=args.judges)
    if score is None:
        die(f"rescore failed; see {out_dir}")
    log(f"rescored {stu_dir.relative_to(rd)}: {out_dir / 'report.md'}")


# ---------------------------------------------------------------- synthesize

def sample_gap_table(run_id: str, k: int) -> str | None:
    """Every gap of every scored sample of iteration k, with how many samples share it; None when
    the iteration has fewer than two scored samples."""
    rows: dict[str, dict] = {}
    totals = []
    for label, _s, cmp_dir in iteration_samples(run_id, k):
        score = read_json(cmp_dir / "score.json")
        if not score:
            continue
        totals.append((label, score["total"]))
        for g in score.get("gaps", []):
            e = rows.setdefault(g["id"], {"samples": [], "tag": g.get("tag"), "severity": g.get("severity"),
                                          "source": g.get("source", ""), "summary": g.get("summary", "")})
            if label not in e["samples"]:
                e["samples"].append(label)
    if len(totals) < 2:
        return None
    n = len(totals)
    severity = {"high": 0, "medium": 1, "low": 2}
    ordered = sorted(rows.items(), key=lambda kv: (-len(kv[1]["samples"]), kv[1]["tag"] != "student_wrong",
                                                   severity.get(kv[1]["severity"], 3), kv[0]))
    out = ["# Gaps across all samples of this iteration", "",
           f"{n} students received the same prompt: " + ", ".join(f"{label} scored {t}" for label, t in totals) + ".",
           "A gap that most samples share is a systematic weakness; a gap that only one sample has may be chance. "
           "Ids from decisions, coverage and rules (source `decision` or `code`) are the same across samples; "
           "ids the judge wrote (source `judge`) may name the same gap differently.", "",
           "| gap id | samples | tag | severity | source | summary |", "|---|---|---|---|---|---|"]
    for gid, e in ordered:
        summary = str(e["summary"]).replace("|", "\\|").replace("\n", " ")[:240]
        out.append(f"| `{gid}` | {len(e['samples'])}/{n} ({', '.join(e['samples'])}) | {e['tag']} | "
                   f"{e['severity']} | {e['source']} | {summary} |")
    return "\n".join(out) + "\n"


def playbook_base(state: dict, k: int) -> dict:
    """Which playbook the synthesizer revises at iteration k (writing the playbook for k+1).

    Normally the latest one (iter-(k-1), used in iteration k). When iteration k scored below the
    best iteration by more than the noise threshold, it reverts to the playbook the best iteration
    used (none for iteration 0). `based_on` and `reverted_from` are iteration indices of
    playbook directories."""
    latest = k - 1 if k > 0 else None
    scores = iteration_scores(state)
    threshold = state.get("noise", {}).get("threshold")
    if k not in scores or threshold is None:
        return {"based_on": latest, "reverted_from": None, "reason": ""}
    best = max(scores, key=lambda j: (scores[j], j))
    if best != k and scores[k] < scores[best] - threshold:
        return {"based_on": best - 1 if best > 0 else None, "reverted_from": latest,
                "reason": f"{scores[k]}, more than the threshold {threshold} below iteration {best} "
                          f"({scores[best]})"}
    return {"based_on": latest, "reverted_from": None, "reason": ""}


def cmd_synthesize(args) -> None:
    state = load_state(args.run)
    verify_frozen(args.run, state)
    check_inputs_unchanged(args.run)
    k = args.iter
    it = state["iters"].get(str(k), {})
    ok = [r for r in it.get("compare", []) if r.get("ok")]
    if not ok:
        die(f"iteration {k} has no successful comparison; run `loop.py compare --iter {k}` first")
    ok.sort(key=lambda r: r["total"])
    chosen = ok[(len(ok) - 1) // 2]
    sfx = "" if chosen["sample"] == "-" else chosen["sample"]
    it_dir = iter_dir(args.run, k)
    stu_dir, cmp_dir, out_dir = it_dir / f"student{sfx}", it_dir / f"compare{sfx}", it_dir / "playbook"
    out_dir.mkdir(parents=True, exist_ok=True)

    lim = CFG["playbook_limits"]
    tmp = out_dir / "_staging"
    tmp.mkdir(exist_ok=True)
    (tmp / "task.md").write_text(task_text(state), encoding="utf-8")
    (tmp / "playbook_rules.md").write_text(prompt(
        "playbook_rules.md", max_span=str(lim["max_span_chars"]),
        max_total=str(lim["max_total_copied_chars"]),
        cap_share_pct=str(int(lim["max_capability_id_share"] * 100)),
        max_lines=str(lim["max_lines"])), encoding="utf-8")
    inputs = {"task.md": tmp / "task.md", "playbook_rules.md": tmp / "playbook_rules.md",
              "reference": oracle_spec(args.run), "student": stu_dir / "spec",
              "trajectory.md": stu_dir / "trajectory.md", "stats.json": stu_dir / "stats.json",
              "report.md": cmp_dir / "report.md", "score.json": cmp_dir / "score.json"}
    if (run_dir(args.run) / "scores.csv").exists():
        inputs["scores.csv"] = run_dir(args.run) / "scores.csv"
    gap_table = sample_gap_table(args.run, k)
    if gap_table:
        (tmp / "sample_gaps.md").write_text(gap_table, encoding="utf-8")
        inputs["sample_gaps.md"] = tmp / "sample_gaps.md"
        log(f"synthesizer gets the gaps of all {len(ok)} samples of iteration {k}; "
            f"report and trajectory from the median sample {chosen['sample']}")
    views_dir = stu_dir / "trajviz" / "trajectory.views"
    if not views_dir.is_dir():
        meta = read_json(stu_dir / "trajectory.run.json", {})
        trajviz_stage(stu_dir, "trajectory", Path(meta.get("workspace", ".")),
                      f"{args.run} student iter {k}{sfx}")
    if views_dir.is_dir():
        picked = tmp / "trajviz"
        picked.mkdir(exist_ok=True)
        for view in CFG.get("trajviz", {}).get("synth_views", []):
            if (views_dir / f"{view}.json").exists():
                shutil.copy2(views_dir / f"{view}.json", picked / f"{view}.json")
        if any(picked.iterdir()):
            inputs["trajviz"] = picked
    base = playbook_base(state, k)
    if base["based_on"] is not None:
        inputs["previous_playbook.md"] = iter_dir(args.run, base["based_on"]) / "playbook" / "playbook.md"
    if base["reverted_from"] is not None:
        inputs["reverted_playbook.md"] = iter_dir(args.run, base["reverted_from"]) / "playbook" / "playbook.md"
        target = "no playbook" if base["based_on"] is None else f"the playbook of iter-{base['based_on']:02d}"
        log(f"iteration {k} scored {base['reason']}; reverting: revising {target} instead of the latest one")
    if k > 0:
        history = [f"## iter-{j:02d}\n\n" + (iter_dir(args.run, j) / "playbook" / "changelog.md")
                   .read_text(encoding="utf-8")
                   for j in range(k) if (iter_dir(args.run, j) / "playbook" / "changelog.md").exists()]
        if history:
            (tmp / "changelog_history.md").write_text("\n\n".join(history), encoding="utf-8")
            inputs["changelog_history.md"] = tmp / "changelog_history.md"

    ws = workspace.build(CFG, args.run, f"iter-{k:02d}-synthesize", inputs)
    sm = model_for(state, "synthesizer")
    meta = run_agent(model=sm, ws=ws, prompt=prompt("synthesize.md"), out_dir=out_dir,
                     label="trajectory", timeout_min=timeout_for(state, "synthesizer"))
    ref_dec = reference_decisions(args.run, state, required=False)
    if ref_dec is None:
        log("warning: no frozen reference decisions; the playbook decision-value check only flags "
            "baseline facts")
    pb = ws / "_outputs" / "playbook.md"
    retries = CFG.get("synth_fix_retries", 0)
    for attempt in range(retries + 1):
        report = playbook_report(args.run, state, pb, ref_dec, out_dir / f"leak-{attempt + 1}",
                                 f"iter-{k:02d}-synthesize-leak{attempt + 1}")
        if report["ok"] or not meta.get("session_id") or attempt == retries:
            break
        problems = report["problems"] + ([f"{len(report['leak_lines'])} line(s) state an open decision or an "
                                          f"HMOS finding, or name HMOS symbols"] if report["leak_lines"] else [])
        log(f"playbook rejected ({'; '.join(problems)}); asking for a rewrite")
        spans = "\n".join(f"- {s}" for s in report.get("spans", [])[:10]) or "- none"
        leaks = "\n".join(f"- line {e['line']}: {e['text'][:160]}  <- {'; '.join(e['reasons'])}"
                          for e in report["leak_lines"][:40]) or "- none"
        meta = run_agent(model=sm, ws=ws, prompt=SYNTH_FIX_PROMPT.format(
            problems="\n".join(f"- {p}" for p in problems), spans=spans, leaks=leaks),
            out_dir=out_dir, label=f"fix{attempt + 1}", timeout_min=timeout_for(state, "synthesizer"),
            resume_session=meta["session_id"])
    stripped = []
    if not report["problems"] and report.get("leak_lines") and pb.exists():
        stripped = report["leak_lines"]
        shutil.copy2(pb, out_dir / "playbook.pre_strip.md")
        pb.write_text(dec.strip_lines(pb.read_text(encoding="utf-8"), [e["line"] for e in stripped]),
                      encoding="utf-8")
        changelog = ws / "_outputs" / "changelog.md"
        note = "\n\n## 泄漏检查自动剔除\n\n" + "\n".join(
            f"- 原第 {e['line']} 行（{'; '.join(e['reasons'])}）：{e['text'][:120]}" for e in stripped) + "\n"
        changelog.write_text((changelog.read_text(encoding="utf-8") if changelog.exists() else "") + note,
                             encoding="utf-8")
        recheck = playbook_report(args.run, state, pb, None, None, None)
        report = {**recheck, "auto_stripped": stripped, "decision_leaks": report["decision_leaks"]}
        log(f"auto-stripped {len(stripped)} flagged line(s) from the playbook")
    write_json(out_dir / "overlap_report.json", report)
    finish_io_stage(args.run, ws, out_dir, ("playbook.md", "changelog.md"), f"synthesizer iter {k}")
    if not report["ok"] and (out_dir / "playbook.md").exists():
        (out_dir / "playbook.md").rename(out_dir / "playbook.rejected.md")
    shutil.rmtree(tmp, ignore_errors=True)
    state = load_state(args.run)
    state["iters"].setdefault(str(k), {})["playbook"] = {
        "ok": report["ok"], "problems": report.get("problems", []), "from_sample": chosen["sample"],
        "lines": report.get("lines"), "copied_chars": report.get("copied_chars"),
        "based_on": base["based_on"], "reverted_from": base["reverted_from"],
        "auto_stripped": [{"line": e["line"], "text": e["text"], "reasons": e["reasons"]} for e in stripped]}
    save_state(args.run, state)
    if report["ok"]:
        log(f"playbook for iteration {k + 1} written: {out_dir / 'playbook.md'} ({report['lines']} lines)")
    else:
        log("playbook REJECTED after retries: " + "; ".join(report["problems"] or
                                                            [f"{len(report['leak_lines'])} leak line(s)"]))


def playbook_report(run_id: str, state: dict, playbook: Path, ref_dec: dict | None,
                    out_dir: Path | None, stage: str | None, strict: bool = False,
                    pb_table: dict | None = None) -> dict:
    """Code checks plus the decision-value leak check (extractor on the playbook, compared with the
    reference decisions). `problems` reject the playbook; `leak_lines` can be stripped."""
    index = hmos_index(run_id)
    ref_caps = list(read_json(oracle_dir(run_id) / "metrics.json", {}).get("baseline_capabilities", {}))
    report = guards.check_playbook(CFG, playbook, oracle_spec(run_id), base_dir(run_id), ref_caps,
                                   task_text(state), index)
    dleaks = []
    if playbook.exists():
        if pb_table is None and out_dir is not None:
            pb_table = extract_playbook(run_id, state, playbook, out_dir, stage, f"leak check {stage}")
        if pb_table is not None:
            lines = playbook.read_text(encoding="utf-8", errors="replace").splitlines()
            dleaks = dec.decision_leaks(pb_table, ref_dec or {}, dec.load_vocab(), lines, strict)
    report["decision_leaks"] = dleaks
    report["leak_lines"] = dec.merge_leaks(report.get("symbol_leaks", []), dleaks)
    report["ok"] = not report["problems"] and not report["leak_lines"]
    return report


def cmd_leak_check(args) -> None:
    """Run the playbook checks on an existing playbook (offline: nothing in state changes)."""
    state = load_state(args.run)
    rd = run_dir(args.run)
    pb = (rd / args.playbook) if args.playbook else iter_dir(args.run, args.iter) / "playbook" / "playbook.md"
    if not pb.exists():
        die(f"no playbook at {pb}")
    name = "leak-strict" if args.strict else "leak"
    out_dir = pb.parent / name
    pb_table = read_json(rd / args.decisions) if args.decisions else None
    ref = reference_decisions(args.run, state, allow_proposed=True)
    report = playbook_report(args.run, state, pb, ref, out_dir, f"{pb.parent.parent.name}-{name}",
                             args.strict, pb_table)
    write_json(out_dir / "leak_report.json", report)
    for p in report["problems"]:
        print(f"PROBLEM {p}")
    for e in report["leak_lines"]:
        print(f"line {e['line']:4d}: {'; '.join(e['reasons'])}\n           {e['text'][:150]}")
    print(f"\n{len(report['leak_lines'])} flagged line(s): {[e['line'] for e in report['leak_lines']]}"
          f"  (decision: {sorted({e['line'] for e in report['decision_leaks']})}, "
          f"symbol: {[e['line'] for e in report['symbol_leaks']]})")
    if args.write_stripped:
        dst = out_dir / "playbook.stripped.md"
        dst.write_text(dec.strip_lines(pb.read_text(encoding="utf-8"),
                                       [e["line"] for e in report["leak_lines"]]), encoding="utf-8")
        log(f"stripped playbook: {dst}")


# ---------------------------------------------------------------- noise / ablation

def sd(xs: list[float]) -> float:
    return statistics.stdev(xs) if len(xs) > 1 else 0.0


def dim_points(values: dict[str, float]) -> dict[str, float]:
    return {d: values[d] * SCORING["weights"][d] / sum(SCORING["weights"].values()) * 100 for d in DIMENSIONS}


def effective_agreement(cmp_dir: Path) -> dict[str, bool]:
    """Per decision item: does it count as agreement (in the table, or by a lenient ruling)."""
    d = read_json(cmp_dir / "decisions_compare.json", {})
    rulings = d.get("rulings", {})
    return {it["id"]: it["status"] == "agree" or rulings.get(it["id"], {}).get("ruling") in dec.COUNTS_AS_AGREEMENT
            for it in d.get("items", [])}


def judge_flips(cmp_dir: Path) -> list[str]:
    by_judge = read_json(cmp_dir / "decisions_compare.json", {}).get("rulings_by_judge") or []
    ids = set().union(*by_judge) if by_judge else set()
    return sorted(i for i in ids if len({r.get(i, {}).get("ruling") for r in by_judge}) > 1)


def cmd_noise(args) -> None:
    """Spread between student samples and between judge passes of one iteration; noise estimates
    and the iteration threshold go to noise.json, noise.md and state.json."""
    state = load_state(args.run)
    k = args.iter
    samples = [(label, read_json(c / "score.json"), c) for label, _s, c in iteration_samples(args.run, k)
               if (c / "score.json").exists()]
    if len(samples) < 2:
        die(f"iteration {k} has {len(samples)} scored sample(s); the noise baseline needs at least 2 "
            f"(student --samples 3, then compare --judges 2)")
    J = min(len(sc.get("judges", [])) for _l, sc, _c in samples)
    if J < 2:
        die(f"iteration {k} was scored with one judge pass; re-run `compare --iter {k} --judges 2`")
    j_iter = args.judges or CFG.get("judges", 1)

    means = [sc["total"] for _l, sc, _c in samples]
    within = statistics.mean(statistics.variance([j["total"] for j in sc["judges"]]) for _l, sc, _c in samples)
    sigma_judge = math.sqrt(within)
    var_student = max(0.0, statistics.variance(means) - within / J)
    sigma_iter = math.sqrt(var_student + within / j_iter)
    threshold = round(2 * math.sqrt(2) * sigma_iter, 1)

    dims = {}
    for d in DIMENSIONS:
        per_sample = [[dim_points(j["dimensions"])[d] for j in sc["judges"]] for _l, sc, _c in samples]
        dims[d] = {"between_samples_sd": round(sd([statistics.mean(x) for x in per_sample]), 2),
                   "within_sample_sd": round(math.sqrt(statistics.mean(statistics.variance(x) for x in per_sample)), 2)}
    agree = {label: effective_agreement(c) for label, _sc, c in samples}
    ids = set().union(*(set(a) for a in agree.values()))
    sample_flips = sorted(i for i in ids if len({a.get(i) for a in agree.values() if i in a}) > 1)
    result = {
        "iter": k, "samples": len(samples), "judges": J, "judges_per_iteration": j_iter,
        "sample_totals": {label: sc["total"] for label, sc, _c in samples},
        "judge_totals": {label: [j["total"] for j in sc["judges"]] for label, sc, _c in samples},
        "between_samples": {"mean": round(statistics.mean(means), 2), "sd": round(sd(means), 2),
                            "min": min(means), "max": max(means)},
        "within_sample": {"pooled_sd": round(sigma_judge, 2),
                          "max_diff": max(max(t) - min(t) for t in
                                          ([j["total"] for j in sc["judges"]] for _l, sc, _c in samples))},
        "dimensions_points": dims,
        "soft_parts": {label: [j.get("soft_parts", {}) for j in sc["judges"]] for label, sc, _c in samples},
        "flips_between_samples": sample_flips,
        "flips_between_judges": {label: judge_flips(c) for label, _sc, c in samples},
        "sigma_judge": round(sigma_judge, 2), "sigma_student": round(math.sqrt(var_student), 2),
        "sigma_iteration": round(sigma_iter, 2), "threshold": threshold,
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    write_json(run_dir(args.run) / "noise.json", result)
    out = ["# 噪声基线", "",
           f"第 {k} 轮，{len(samples)} 个 student 样本 × 每样本 {J} 次独立评审（裁定 + 软性分项）。", "",
           "| 样本 | 均值 | 各评审总分 |", "|---|---|---|"]
    out += [f"| {label} | {sc['total']} | {', '.join(str(j['total']) for j in sc['judges'])} |"
            for label, sc, _c in samples]
    out += ["", f"- 样本间：均值 {result['between_samples']['mean']}，标准差 {result['between_samples']['sd']}"
            f"（{min(means)} – {max(means)}）",
            f"- 样本内（评审间）：合并标准差 {result['within_sample']['pooled_sd']}，最大差 "
            f"{result['within_sample']['max_diff']}",
            f"- σ_judge = sqrt(样本内方差均值) = {result['sigma_judge']}",
            f"- σ_student = sqrt(var(样本均值) − σ²_judge / {J}) = {result['sigma_student']}",
            f"- 单轮分数（1 个样本、{j_iter} 次评审）σ = sqrt(σ²_student + σ²_judge / {j_iter}) = "
            f"{result['sigma_iteration']}",
            f"- **轮间阈值 = 2 × √2 × σ = {threshold}**：两轮分数之差超过它才算显著；"
            f"消融实验改用各组均值之差的标准误。", "",
            "## 各维度（分值，满分为权重）", "", "| 维度 | 样本间标准差 | 样本内标准差 |", "|---|---|---|"]
    out += [f"| {d} | {v['between_samples_sd']} | {v['within_sample_sd']} |" for d, v in dims.items()]
    out += ["", "## 结果翻转的决策项", "",
            f"- 样本之间（是否计为一致）：{', '.join(f'`{i}`' for i in sample_flips) or '无'}"]
    out += [f"- 样本 {label} 的评审之间（裁定不同）：{', '.join(f'`{i}`' for i in f) or '无'}"
            for label, f in result["flips_between_judges"].items()]
    (run_dir(args.run) / "noise.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    state = load_state(args.run)
    state["noise"] = {key: result[key] for key in ("iter", "samples", "judges", "judges_per_iteration",
                                                   "sigma_judge", "sigma_student", "sigma_iteration",
                                                   "threshold", "measured_at")}
    save_state(args.run, state)
    log(f"noise: sigma_judge {result['sigma_judge']}, sigma_student {result['sigma_student']}, "
        f"sigma per iteration {result['sigma_iteration']}; threshold {threshold} "
        f"({run_dir(args.run) / 'noise.md'})")


ARMS = ("none", "full", "process_only")
ARM_PAIRS = (("process_only", "none"), ("full", "process_only"), ("full", "none"))


def student_valid(stu_dir: Path) -> bool:
    meta = read_json(stu_dir / "trajectory.run.json", {})
    leak = read_json(stu_dir / "guards.json", {}).get("leak", {})
    return bool(meta.get("ok")) and not meta.get("incomplete") and bool(leak.get("ok")) and \
        (stu_dir / "spec" / "openspec").is_dir()


def arm_summary(scores: list[dict], cmp_dirs: list[Path]) -> dict:
    totals = [s["total"] for s in scores]
    points = [dim_points({d: s["dimensions"][d]["value"] for d in DIMENSIONS}) for s in scores]
    groups = [*dec.GROUPS, *dec.ALL_KINDS]
    return {"n": len(scores), "mean": round(statistics.mean(totals), 2), "sd": round(sd(totals), 2),
            "min": min(totals), "max": max(totals), "totals": totals,
            "dimensions": {d: round(statistics.mean(p[d] for p in points), 2) for d in DIMENSIONS},
            "agreement": {g: round(statistics.mean(s["agreement"][g]["value"] for s in scores), 4)
                          for g in groups if all(g in s.get("agreement", {}) for s in scores)},
            "gaps": sorted(majority_gaps(scores)), "compare_dirs": [str(c) for c in cmp_dirs]}


def cmd_ablate(args) -> None:
    """Arms judged the same way: none (the iteration-0 samples, no new runs) against full (fresh
    students with the selected playbook); optionally process_only (the same playbook with every line
    a strict leak pass flags removed)."""
    state = load_state(args.run)
    verify_frozen(args.run, state)
    check_inputs_unchanged(args.run)
    rd, judges, samples = run_dir(args.run), args.judges or CFG.get("judges", 1), max(2, args.samples)
    new_arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    if not new_arms or any(a not in ARMS[1:] for a in new_arms):
        die(f"--arms takes a comma-separated subset of {', '.join(ARMS[1:])}")
    if args.playbook == "top":
        best = best_playbook_iter(state)
        if best is None:
            die("no iteration with a playbook has a score yet; run `loop.py iterate` first")
        src = best - 1
    else:
        m = re.fullmatch(r"iter-(\d+)", args.playbook)
        if not m:
            die("--playbook is `top` or `iter-NN` (the iteration whose playbook/ holds it)")
        src = int(m.group(1))
    pb = iter_dir(args.run, src) / "playbook" / "playbook.md"
    if not pb.exists():
        die(f"no playbook at {pb}")
    name = f"iter-{src:02d}"
    abl = rd / "ablation"
    previous = state.get("ablation", {}).get("playbook")
    if previous and previous != name:
        if not args.force:
            die(f"runs/{args.run}/ablation/ tests playbook {previous}; pass --force to replace it with {name}")
        remove_tree(abl)
    abl.mkdir(parents=True, exist_ok=True)
    full = abl / "playbook.full.md"
    if not full.exists():
        shutil.copy2(pb, full)
    ref = reference_decisions(args.run, state)
    process_only = abl / "playbook.process_only.md"
    if "process_only" in new_arms and not process_only.exists():
        report = playbook_report(args.run, state, full, ref, abl / "strict-leak", "ablation-strict-leak", strict=True)
        write_json(abl / "process_only_strip.json", report)
        process_only.write_text(dec.strip_lines(full.read_text(encoding="utf-8"),
                                                [e["line"] for e in report["leak_lines"]]), encoding="utf-8")
        log(f"process-only playbook: {len(report['leak_lines'])} of {report.get('lines')} lines removed "
            f"({process_only})")
    state = load_state(args.run)
    state["ablation"] = {"playbook": name, "arms": ["none", *new_arms], "samples": samples, "judges": judges,
                         "based_on_score": iteration_scores(state).get(src + 1)}
    save_state(args.run, state)

    none = [(c, read_json(c / "score.json")) for _l, _s, c in iteration_samples(args.run, 0)
            if (c / "score.json").exists()]
    if len(none) < 2:
        die("the none arm reuses the iteration-0 samples and needs at least 2 of them (Phase B)")
    playbooks = {"full": full, "process_only": process_only}
    texts = {arm: playbook_prompt(state, playbooks[arm].read_text(encoding="utf-8")) for arm in new_arms}
    jobs = [(arm, s) for arm in texts for s in range(1, samples + 1)]

    def student_job(arm: str, s: int):
        sdir = abl / arm / f"student-s{s}"
        if student_valid(sdir):
            return
        run_student(args.run, state, sdir, f"ablation-{arm}-student-s{s}", texts[arm], f"ablation {arm} s{s}", f"-s{s}")

    def compare_job(arm: str, s: int):
        sdir, cdir = abl / arm / f"student-s{s}", abl / arm / f"compare-s{s}"
        if not student_valid(sdir):
            log(f"ablation {arm} s{s}: no valid student run; left out")
            return None
        old = read_json(cdir / "score.json")
        if old and (len(old.get("judges", [])) or 1) == judges:
            return cdir, old
        sc = score_sample(args.run, state, 0, f"ablation-{arm}-compare-s{s}", sdir, cdir, ref, judges=judges)
        return (cdir, sc) if sc else None

    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        list(pool.map(lambda j: student_job(*j), jobs))
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        scored = dict(zip(jobs, pool.map(lambda j: compare_job(*j), jobs)))

    arms = {"none": arm_summary([s for _c, s in none], [c for c, _s in none])}
    for arm in texts:
        got = [scored[(arm, s)] for s in range(1, samples + 1) if scored.get((arm, s))]
        if len(got) < 2:
            die(f"ablation arm {arm} has {len(got)} scored sample(s); at least 2 are needed")
        arms[arm] = arm_summary([s for _c, s in got], [c for c, _s in got])
    pairs = []
    for a, b in ARM_PAIRS:
        if a not in arms or b not in arms:
            continue
        A, B = arms[a], arms[b]
        se = math.sqrt(A["sd"] ** 2 / A["n"] + B["sd"] ** 2 / B["n"])
        diff = round(A["mean"] - B["mean"], 2)
        pairs.append({"a": a, "b": b, "diff": diff, "se": round(se, 2), "two_se": round(2 * se, 2),
                      "significant": se > 0 and abs(diff) > 2 * se,
                      "dimensions": {d: round(A["dimensions"][d] - B["dimensions"][d], 2) for d in DIMENSIONS},
                      "agreement": {g: round(A["agreement"][g] - B["agreement"][g], 4)
                                    for g in A["agreement"] if g in B["agreement"]},
                      "gaps_closed": sorted(set(B["gaps"]) - set(A["gaps"])),
                      "gaps_opened": sorted(set(A["gaps"]) - set(B["gaps"]))})
    result = {"playbook": name, "playbook_iteration_score": iteration_scores(state).get(src + 1),
              "samples": samples, "judges": judges, "arms": arms, "pairs": pairs,
              "noise": state.get("noise"),
              "process_only_lines_removed": len(read_json(abl / "process_only_strip.json", {}).get("leak_lines", []))
              if "process_only" in arms else None}
    write_json(abl / "ablation.json", result)
    (abl / "report.md").write_text(render_ablation(result), encoding="utf-8")
    for p in pairs:
        log(f"ablation {p['a']} - {p['b']}: {p['diff']:+.1f} (2 SE {p['two_se']}) "
            f"{'significant' if p['significant'] else 'not significant'}")
    log(f"ablation report: {abl / 'report.md'}")


def render_ablation(r: dict) -> str:
    label = {"none": "无 playbook", "full": "完整 playbook", "process_only": "仅过程（剔除答案行）"}
    out = ["# 消融实验", "",
           f"被测 playbook：`{r['playbook']}`（它所在轮的原始分数 {r['playbook_iteration_score']}；该分数因择优而偏高，"
           f"这里用新样本重测）。无 playbook 组复用第 0 轮的基线样本。每组每个样本由 {r['judges']} 次独立评审打分，"
           f"样本分为评审均值。"
           + (f"仅过程组剔除了严格泄漏检查标出的 {r['process_only_lines_removed']} 行"
              f"（任何决策值，包括 AGENTS.md 已定的；任何 HMOS 符号；HMOS 代码行为结论）。"
              if r.get("process_only_lines_removed") is not None else ""), "",
           "| 组 | n | 均值 | 标准差 | 范围 |", "|---|---|---|---|---|"]
    for arm, a in r["arms"].items():
        out.append(f"| {label[arm]} | {a['n']} | {a['mean']} | {a['sd']} | {a['min']} – {a['max']} |")
    out += ["", "## 两两比较", "",
            "差值超过 2 × SE_diff 才算显著，SE_diff = sqrt(s²_a / n_a + s²_b / n_b)，用各组自己的样本间离散度。", "",
            "| 比较 | 含义 | 差值 | 2 × SE | 结论 |", "|---|---|---|---|---|"]
    meaning = {("process_only", "none"): "教过程的价值", ("full", "process_only"): "残留答案内容的价值（应接近 0）",
               ("full", "none"): "playbook 的总效果"}
    for p in r["pairs"]:
        out.append(f"| {label[p['a']]} − {label[p['b']]} | {meaning[(p['a'], p['b'])]} | {p['diff']:+.1f} | "
                   f"{p['two_se']} | {'显著' if p['significant'] else '不显著'} |")
    out += ["", "## 各维度（分值差）", "", "| 维度 | " + " | ".join(f"{label[p['a']]} − {label[p['b']]}"
                                                         for p in r["pairs"]) + " |",
            "|---|" + "---|" * len(r["pairs"])]
    for d in DIMENSIONS:
        out.append(f"| {d} | " + " | ".join(f"{p['dimensions'][d]:+.2f}" for p in r["pairs"]) + " |")
    out += ["", "## 决策一致率（分组与类别）", "",
            "| 分组 / 类别 | " + " | ".join(label[a] for a in r["arms"]) + " |", "|---|" + "---|" * len(r["arms"])]
    for g in r["arms"]["none"]["agreement"]:
        out.append(f"| {g} | " + " | ".join(f"{a['agreement'].get(g, '-')}" for a in r["arms"].values()) + " |")
    out += ["", "## 差距 id 变化（按多数样本计）", ""]
    for p in r["pairs"]:
        out.append(f"- {label[p['a']]} 相对 {label[p['b']]}：关闭 "
                   f"{', '.join(f'`{i}`' for i in p['gaps_closed']) or '无'}；新出现 "
                   f"{', '.join(f'`{i}`' for i in p['gaps_opened']) or '无'}")
    noise = r.get("noise") or {}
    if noise:
        base_sd = r["arms"]["none"]["sd"]
        wide = [label[a] for a, v in r["arms"].items() if a != "none" and base_sd and v["sd"] > 2 * base_sd]
        out += ["", "## 与噪声基线的对照", "",
                f"噪声基线 σ_student {noise.get('sigma_student')}，轮间阈值 {noise.get('threshold')}。"
                + (f"{'、'.join(wide)} 的样本间离散度超过无 playbook 组的两倍，建议按带 playbook 的离散度更新阈值。"
                   if wide else "各组离散度与无 playbook 组相当，阈值无需更新。")]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- iterate / status / smoke

def ensure_playbook(run_id: str, k: int) -> None:
    if not load_state(run_id)["iters"].get(str(k), {}).get("playbook", {}).get("ok"):
        cmd_synthesize(argparse.Namespace(run=run_id, iter=k))
        if not load_state(run_id)["iters"][str(k)].get("playbook", {}).get("ok"):
            die(f"iteration {k}: no acceptable playbook; inspect {iter_dir(run_id, k) / 'playbook'}")


def best_playbook_iter(state: dict) -> int | None:
    """Iteration with the highest raw score among those that used a playbook (k >= 1)."""
    scores = {j: s for j, s in iteration_scores(state).items() if j >= 1}
    return max(scores, key=lambda j: (scores[j], j)) if scores else None


def cmd_iterate(args) -> None:
    """Run a fixed number of iterations (no early stop): student -> compare -> synthesize. The last
    iteration writes no playbook; a later `iterate --start` writes it first."""
    state = load_state(args.run)
    verify_frozen(args.run, state)
    judges = args.judges or CFG.get("judges", 1)
    last = args.start + (args.iters or CFG["iterations"]) - 1
    for k in range(args.start, last + 1):
        if k > 0:
            ensure_playbook(args.run, k - 1)
        state = load_state(args.run)
        it = state["iters"].get(str(k), {})
        if not any(r.get("valid") for r in it.get("student", [])):
            cmd_student(argparse.Namespace(run=args.run, iter=k, samples=args.samples, dry_run=False))
            state = load_state(args.run)
            if not any(r.get("valid") for r in state["iters"][str(k)]["student"]):
                die(f"iteration {k}: no valid student run; inspect {iter_dir(args.run, k)}")
        if state["iters"][str(k)].get("score") is None:
            cmd_compare(argparse.Namespace(run=args.run, iter=k, judges=judges))
            state = load_state(args.run)
            if state["iters"][str(k)].get("score") is None:
                die(f"iteration {k}: comparison failed; inspect {iter_dir(args.run, k)}")
        if k < last:
            ensure_playbook(args.run, k)
    state = load_state(args.run)
    best = best_playbook_iter(state)
    log(f"finished iterations {args.start}..{last}" + (
        f"; highest raw score with a playbook: iteration {best} ({iteration_scores(state)[best]}), playbook "
        f"{iter_dir(args.run, best - 1) / 'playbook' / 'playbook.md'}; `loop.py ablate` tests whether it helps"
        if best is not None else ""))


def cmd_reset(args) -> None:
    state = load_state(args.run)
    gone = sorted(int(k) for k in state["iters"] if int(k) >= args.from_iter)
    for k in gone:
        remove_tree(iter_dir(args.run, k))
        del state["iters"][str(k)]
    save_state(args.run, state)
    csv_path = run_dir(args.run) / "scores.csv"
    if csv_path.exists():
        write_csv(csv_path, [r for r in read_csv(csv_path) if int(r["iter"]) < args.from_iter])
    log(f"discarded iterations {gone or 'none'} of run '{args.run}'")


def cmd_status(args) -> None:
    state = load_state(args.run)
    o = state["oracle"]
    print(f"run {args.run}{' (smoke)' if smoke(state) else ''}")
    print(f"  oracle: {o.get('status')}  validate={o.get('validate_ok')}  frozen={state.get('frozen')}"
          f"  session={o.get('session_id')}")
    if o.get("problems"):
        print(f"  oracle problems: {'; '.join(o['problems'])}")
    if state.get("reference_decisions"):
        rdec = state["reference_decisions"]
        print(f"  reference decisions: frozen={rdec.get('frozen')}  stated={rdec.get('stated')}"
              + (f"  copied from {rdec['copied_from']}" if rdec.get("copied_from") else ""))
    noise = state.get("noise")
    if noise:
        print(f"  noise (iteration {noise['iter']}, {noise['samples']} samples x {noise['judges']} judges): "
              f"sigma_judge {noise['sigma_judge']}  sigma_student {noise['sigma_student']}  "
              f"sigma_iteration {noise['sigma_iteration']}  threshold {noise['threshold']}")
    for k in sorted(state["iters"], key=int):
        it = state["iters"][k]
        st = ", ".join(f"{r['sample']}:{'valid' if r.get('valid') else 'INVALID'}"
                       for r in it.get("student", []))
        pb = it.get("playbook", {})
        vs = it.get("vs_best")
        mark = f"  vs best {vs['delta']:+.1f}{' ' + vs['mark'] if vs.get('mark') else ''}" if vs else ""
        based = f" (based on iter-{pb['based_on']:02d})" if pb.get("based_on") is not None else ""
        reverted = f", reverted from iter-{pb['reverted_from']:02d}" if pb.get("reverted_from") is not None else ""
        stripped = f", {len(pb['auto_stripped'])} line(s) auto-stripped" if pb.get("auto_stripped") else ""
        print(f"  iter {int(k):02d}: student [{st}]  score={it.get('score')}{mark}  "
              f"playbook={'ok' if pb.get('ok') else ('rejected' if pb else '-')}{based}{reverted}{stripped}")
    rows = read_csv(run_dir(args.run) / "scores.csv")
    cols = ("iter", "sample", "total", "vs_best", *DIMENSIONS, "judge_spread", "gaps_closed", "gaps_reopened")
    if rows:
        print("\n  " + "  ".join(cols))
        for r in rows:
            print("  " + "  ".join(str(r.get(c, "")) for c in cols))
    abl = read_json(run_dir(args.run) / "ablation" / "ablation.json")
    if abl:
        print("\n  ablation (" + abl["playbook"] + "): " + "  ".join(
            f"{a} {v['mean']} (n={v['n']})" for a, v in abl["arms"].items()))
        for p in abl["pairs"]:
            print(f"    {p['a']} - {p['b']}: {p['diff']:+.1f} (2 SE {p['two_se']}) "
                  f"{'significant' if p['significant'] else 'not significant'}")


def cmd_trajviz(args) -> None:
    rd = run_dir(args.run)
    stages = [rd / args.stage] if args.stage else \
        sorted({p.parent for p in rd.rglob("*.run.json") if "transcripts" not in p.parts})
    for out_dir in stages:
        for label in run_labels(out_dir):
            meta = read_json(out_dir / f"{label}.run.json", {})
            title = f"{args.run} {out_dir.relative_to(rd).as_posix()} ({label})"
            trajviz_stage(out_dir, label, Path(meta.get("workspace", ".")), title)
            html = out_dir / "trajviz" / f"{label}.html"
            log(f"{out_dir.relative_to(rd)}/{label}: {out_dir / 'trajviz' / (label + '.trajviz.json')}"
                + (f"  report: {html}" if html.exists() else ""))


def cmd_smoke(args) -> None:
    if not (run_dir(args.run) / "state.json").exists():
        cmd_prepare(argparse.Namespace(run=args.run, force=False, smoke=True, reference_from=None))
    state = load_state(args.run)
    if not smoke(state):
        die(f"run '{args.run}' is not a smoke run")
    if state["oracle"].get("status") in ("pending", "failed"):
        cmd_oracle(argparse.Namespace(run=args.run, revise=None, revise_file=None))
    state = load_state(args.run)
    if not state.get("reference_decisions", {}).get("frozen") and \
            not (oracle_dir(args.run) / "decisions.proposed.json").exists():
        cmd_extract(argparse.Namespace(run=args.run, target="oracle", passes=1, out=None))
    if not state.get("frozen") or not state.get("reference_decisions", {}).get("frozen"):
        cmd_freeze(argparse.Namespace(run=args.run, force=True))
    verify_frozen(args.run, load_state(args.run))
    if not load_state(args.run)["iters"].get("0", {}).get("student"):
        cmd_student(argparse.Namespace(run=args.run, iter=0, samples=1, dry_run=False))
    if load_state(args.run)["iters"]["0"].get("score") is None:
        cmd_compare(argparse.Namespace(run=args.run, iter=0, judges=1))
    if not load_state(args.run)["iters"]["0"].get("playbook"):
        cmd_synthesize(argparse.Namespace(run=args.run, iter=0))

    state = load_state(args.run)
    checks = []
    rd = run_dir(args.run)
    sfx = sample_label(state, 1, 1)
    for stage in ("oracle", f"iter-00/student{sfx}", f"iter-00/compare{sfx}/decisions",
                  f"iter-00/compare{sfx}/soft", "iter-00/playbook"):
        meta = read_json(rd / stage / "trajectory.run.json", {})
        checks.append((f"{stage}: model reported '{meta.get('model_reported')}'", meta.get("model_ok")))
        checks.append((f"{stage}: run finished", meta.get("has_result") and not meta.get("is_error")))
        checks.append((f"{stage}: transcript copied", bool(meta.get("transcript_copy"))))
        checks.append((f"{stage}: trajectory.md rendered", (rd / stage / "trajectory.md").exists()))
    for stage in ("oracle", f"iter-00/student{sfx}"):
        g = read_json(rd / stage / "guards.json", {})
        checks.append((f"{stage}: only openspec/ written", g.get("no_code", {}).get("ok")))
        checks.append((f"{stage}: openspec validate", g.get("validate", {}).get("ok")))
        checks.append((f"{stage}: leak-free", g.get("leak", {}).get("ok")))
    checks.append(("oracle frozen and manifest verified", state.get("frozen")))
    checks.append(("reference decisions frozen", state.get("reference_decisions", {}).get("frozen")))
    checks.append(("score.json valid and scored", state["iters"]["0"].get("score") is not None))
    checks.append(("playbook accepted", state["iters"]["0"].get("playbook", {}).get("ok")))
    if state["iters"]["0"].get("playbook", {}).get("ok"):
        text = student_prompt(state, args.run, 1)
        checks.append((f"iteration-1 prompt includes the playbook ({len(text.encode('utf-8'))} bytes)",
                       "# Playbook" in text))
    print("\nsmoke checks:")
    for label, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not all(ok for _, ok in checks):
        sys.exit(2)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("prepare", help="create runs/<run>/ with inputs.lock.json and the base snapshot")
    p.add_argument("--run", required=True)
    p.add_argument("--force", action="store_true")
    p.add_argument("--smoke", action="store_true", help="use the small smoke task and smoke model")
    p.add_argument("--reference-from", metavar="RUN",
                   help="reuse RUN's frozen reference spec, manifest and reference decisions (no oracle run)")
    p.set_defaults(fn=cmd_prepare)

    p = sub.add_parser("oracle", help="run the oracle, or revise its spec with --revise")
    p.add_argument("--run", required=True)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--revise", help="reviewer feedback; resumes the oracle session")
    g.add_argument("--revise-file", help="file containing reviewer feedback")
    p.set_defaults(fn=cmd_oracle)

    p = sub.add_parser("freeze", help="hash the reviewed oracle spec and reference decisions, make them "
                                      "read-only (an already frozen spec gets its decisions frozen)")
    p.add_argument("--run", required=True)
    p.add_argument("--force", action="store_true", help="freeze even if validation fails")
    p.set_defaults(fn=cmd_freeze)

    p = sub.add_parser("extract", help="extract a decision table from a spec or a playbook")
    p.add_argument("--run", required=True)
    p.add_argument("--target", required=True,
                   help="run-relative directory holding spec/ (oracle, iter-00/student) or playbook .md")
    p.add_argument("--passes", type=int, default=2, help="independent passes, run in parallel (default 2)")
    p.add_argument("--out", help="run-relative output directory (default <target>/decisions)")
    p.set_defaults(fn=cmd_extract)

    p = sub.add_parser("student", help="run the student for one iteration")
    p.add_argument("--run", required=True)
    p.add_argument("--iter", type=int, required=True)
    p.add_argument("--samples", type=int, default=1)
    p.add_argument("--dry-run", action="store_true", help="print the prompt and exit")
    p.set_defaults(fn=cmd_student)

    p = sub.add_parser("compare", help="score the student spec(s) of one iteration")
    p.add_argument("--run", required=True)
    p.add_argument("--iter", type=int, required=True)
    p.add_argument("--judges", type=int, help="independent judge passes per sample (default: config judges)")
    p.set_defaults(fn=cmd_compare)

    p = sub.add_parser("noise", help="student and judge spread of one iteration; sets the iteration threshold")
    p.add_argument("--run", required=True)
    p.add_argument("--iter", type=int, default=0)
    p.add_argument("--judges", type=int, help="judge passes per later iteration score (default: config judges)")
    p.set_defaults(fn=cmd_noise)

    p = sub.add_parser("ablate", help="none / full / process-only playbook arms on fresh samples")
    p.add_argument("--run", required=True)
    p.add_argument("--playbook", default="top", help="`top` (highest raw score) or iter-NN")
    p.add_argument("--samples", type=int, default=3, help="fresh students per new arm")
    p.add_argument("--judges", type=int, help="judge passes per sample (default: config judges)")
    p.add_argument("--arms", default="full",
                   help="new arms besides none, comma-separated: full (default), process_only")
    p.add_argument("--force", action="store_true", help="replace an ablation of another playbook")
    p.set_defaults(fn=cmd_ablate)

    p = sub.add_parser("rescore", help="score an existing student spec again into iter-KK/<out>/ "
                                       "(state.json and scores.csv untouched)")
    p.add_argument("--run", required=True)
    p.add_argument("--iter", type=int, required=True)
    p.add_argument("--out", default="rescore", help="output directory name under iter-KK/ (default rescore)")
    p.add_argument("--student", help="run-relative student directory (default iter-KK/student)")
    p.add_argument("--student-decisions", help="run-relative decisions.json to reuse instead of extracting")
    p.add_argument("--reuse", action="store_true",
                   help="reuse the extraction, rulings and soft score already in iter-KK/<out>/ "
                        "(for changes to the scoring code only)")
    p.add_argument("--judges", type=int, default=1, help="independent judge passes (default 1)")
    p.set_defaults(fn=cmd_rescore)

    p = sub.add_parser("synthesize", help="write the playbook for the next iteration")
    p.add_argument("--run", required=True)
    p.add_argument("--iter", type=int, required=True)
    p.set_defaults(fn=cmd_synthesize)

    p = sub.add_parser("leak-check", help="run the playbook checks on an existing playbook")
    p.add_argument("--run", required=True)
    p.add_argument("--iter", type=int, default=0, help="checks iter-KK/playbook/playbook.md")
    p.add_argument("--playbook", help="run-relative playbook path instead")
    p.add_argument("--strict", action="store_true",
                   help="flag every stated decision value, settled by AGENTS.md or not")
    p.add_argument("--decisions", help="run-relative playbook decisions.json to reuse instead of extracting")
    p.add_argument("--write-stripped", action="store_true", help="also write the playbook without flagged lines")
    p.set_defaults(fn=cmd_leak_check)

    p = sub.add_parser("iterate", help="student -> compare -> synthesize for a fixed number of iterations")
    p.add_argument("--run", required=True)
    p.add_argument("--iters", type=int, default=None, help="default: config.json iterations")
    p.add_argument("--start", type=int, default=0)
    p.add_argument("--samples", type=int, default=1)
    p.add_argument("--judges", type=int, help="judge passes per sample (default: config judges)")
    p.set_defaults(fn=cmd_iterate)

    p = sub.add_parser("reset", help="discard iterations K and later (outputs, state, score rows)")
    p.add_argument("--run", required=True)
    p.add_argument("--from-iter", type=int, required=True)
    p.set_defaults(fn=cmd_reset)

    p = sub.add_parser("status", help="show the state and score history of a run")
    p.add_argument("--run", required=True)
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("trajviz", help="(re)export agent runs for TrajViz: JSON, views, HTML report")
    p.add_argument("--run", required=True)
    p.add_argument("--stage", help="e.g. oracle or iter-00/student (default: every stage)")
    p.set_defaults(fn=cmd_trajviz)

    p = sub.add_parser("smoke", help="end-to-end plumbing test with the smoke task")
    p.add_argument("--run", required=True)
    p.set_defaults(fn=cmd_smoke)

    args = ap.parse_args()
    set_parallel_limit(CFG.get("max_parallel_agents", 8))
    args.fn(args)


if __name__ == "__main__":
    main()
