"""Running the oracle, student, extractor, judge and synthesizer agents, and finishing their stages."""

from __future__ import annotations

import json

from pathlib import Path

from lib import guards, render_traj, spec_metrics, trajviz_export
from lib.common import ROOT, copy_tree, log, read_json, remove_tree, write_json, write_text_atomic
from lib.runner import run_agent

from .core import CFG, base_dir, hmos_index, model_for, timeout_for


FIX_PROMPT = """`_outputs/{name}` does not pass the checker:

{errors}

Fix `_outputs/{name}`{also}. Do not modify anything else.
"""


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
            write_text_atomic(out_dir / name, (ws / "_outputs" / name).read_text(encoding="utf-8"))
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
