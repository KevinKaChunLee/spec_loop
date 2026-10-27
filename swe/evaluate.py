"""Evaluate stage: score a stage's patches with the official SWE-bench harness (in the smoke test, a
check command per task), write eval.json beside each attempt and the stage's rows of results.csv.

An empty patch is unresolved without running the harness. A patch the harness could not evaluate
(no report) gets `resolved: null`, and the command stops until it is evaluated."""

from __future__ import annotations

import csv
import io
import json
import shutil
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path

from lib.common import die, load_state, log, read_json, run_dir, state_update, timestamp, write_json, write_text_atomic

from .core import CFG, attempt_dir, json_digest, tasks
from .env import docker_available

RESULT_FIELDS = ["stage", "role", "instance_id", "sample", "playbook", "valid", "resolved", "applied", "f2p_pass",
                 "f2p_total", "p2p_fail", "patch_lines", "attempts", "nudges", "timed_out", "finish_reason", "minutes",
                 "tool_calls", "input_tokens", "output_tokens", "problems"]


def stage_attempts(run_id: str, stage: str) -> list[tuple[dict, Path]]:
    """The current attempt of every task and sample the stage was last solved with (attempts set
    aside as sN.attemptK, and directories of other tasks or samples, are not part of it)."""
    s = load_state(run_id).get("stages", {}).get(stage)
    if not s:
        return []
    out = []
    for iid in s["tasks"]:
        for sample in range(1, s["samples"] + 1):
            d = attempt_dir(run_id, stage, iid, sample)
            rec = read_json(d / "attempt.json")
            if rec:
                out.append((rec, d))
    return out


def parse_report(path: Path, iid: str) -> dict:
    data = read_json(path)
    if not data or iid not in data:
        return {"resolved": None, "error": f"no harness report at {path}"}
    r = data[iid]
    ts = r.get("tests_status") or {}
    f2p, p2p = ts.get("FAIL_TO_PASS") or {}, ts.get("PASS_TO_PASS") or {}
    return {"resolved": bool(r.get("resolved")), "applied": bool(r.get("patch_successfully_applied")),
            "f2p_pass": len(f2p.get("success", [])), "f2p_fail": f2p.get("failure", []),
            "p2p_fail": p2p.get("failure", []), "infra_failure": r.get("infra_failure"),
            "test_output": str(path.parent / "test_output.txt")}


def run_harness(run_id: str, harness_id: str, ids: list[str], predictions: str) -> Path:
    """Run swebench.harness.run_evaluation in runs/<run>/harness; returns its log directory."""
    why = docker_available()
    if why:
        die(f"the SWE-bench harness needs Docker: {why} (see README_swe.md, setup)")
    hdir = run_dir(run_id) / "harness"
    (hdir / "reports").mkdir(parents=True, exist_ok=True)
    cmd = [CFG["python"], "-m", "swebench.harness.run_evaluation", "-d", str(run_dir(run_id) / "dataset.json"),
           "-i", *ids, "-p", predictions, "-id", harness_id, "--max_workers", str(CFG["harness"]["max_workers"]),
           "-t", str(CFG["harness"]["timeout_s"]), "--report_dir", str(hdir / "reports")]
    log(f"harness {harness_id}: {len(ids)} task(s)")
    with open(hdir / f"{harness_id}.log", "w", encoding="utf-8") as logf:
        rc = subprocess.run(cmd, cwd=hdir, stdout=logf, stderr=subprocess.STDOUT).returncode
    if rc != 0:
        log(f"warning: harness {harness_id} exited {rc}; see {hdir / f'{harness_id}.log'}")
    return hdir / "logs" / "run_evaluation" / harness_id


def harness_eval(run_id: str, stage: str, sample: int, items: list[tuple[dict, Path]]) -> dict[str, dict]:
    model_name = f"{run_id}.{stage}.s{sample}"
    preds = [{"instance_id": rec["instance_id"], "model_name_or_path": model_name,
              "model_patch": (d / "patch.diff").read_text(encoding="utf-8")} for rec, d in items]
    harness_id = f"{model_name}.{json_digest(preds)[:10]}"
    pred_path = run_dir(run_id) / "harness" / "predictions" / f"{harness_id}.jsonl"
    write_text_atomic(pred_path, "".join(json.dumps(p) + "\n" for p in preds))
    logs = run_harness(run_id, harness_id, [p["instance_id"] for p in preds], str(pred_path))
    return {rec["instance_id"]: {**parse_report(logs / model_name / rec["instance_id"] / "report.json",
                                                rec["instance_id"]), "harness_id": harness_id}
            for rec, _d in items}


def local_eval(run_id: str, items: list[tuple[dict, Path]]) -> dict[str, dict]:
    """Smoke test: apply the patch to a copy of the task's repository and run its check command."""
    by_id = {t["instance_id"]: t for split in ("train", "test") for t in tasks(run_id, split)}
    out = {}
    for rec, d in items:
        task = by_id[rec["instance_id"]]
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "repo"
            shutil.copytree(task["local_repo"], work)
            applied = subprocess.run(["git", "apply", str(d / "patch.diff")], cwd=work, capture_output=True).returncode == 0
            check = subprocess.run(["bash", "-c", task["check"]], cwd=work, capture_output=True, text=True, timeout=300)
            output = check.stdout + check.stderr
        (d / "test_output.txt").write_text(output, encoding="utf-8")
        ok = applied and check.returncode == 0
        out[rec["instance_id"]] = {"resolved": ok, "applied": applied, "f2p_pass": int(ok),
                                   "f2p_fail": [] if ok else [task["check"]], "p2p_fail": [],
                                   "test_output": str(d / "test_output.txt")}
    return out


def gold_check(run_id: str, ids: list[str]) -> dict[str, bool | None]:
    """Does every task's gold patch resolve in the harness (images, environment, tests all sound)?"""
    logs = run_harness(run_id, f"{run_id}.gold", ids, "gold")
    return {iid: parse_report(logs / "gold" / iid / "report.json", iid)["resolved"] for iid in ids}


def result_row(rec: dict, ev: dict | None) -> dict:
    ev = ev or {}
    usage = rec.get("usage") or {}
    return {"stage": rec["stage"], "role": rec["role"], "instance_id": rec["instance_id"], "sample": rec["sample"],
            "playbook": (rec.get("playbook_sha256") or "")[:10], "valid": rec["valid"], "resolved": ev.get("resolved"),
            "applied": ev.get("applied"), "f2p_pass": ev.get("f2p_pass"),
            "f2p_total": (ev.get("f2p_pass") or 0) + len(ev.get("f2p_fail") or []) if ev else None,
            "p2p_fail": len(ev.get("p2p_fail") or []) if ev else None, "patch_lines": rec["patch_lines"],
            "attempts": rec["attempts"], "nudges": rec["nudges"], "timed_out": rec["timed_out"],
            "finish_reason": rec["finish_reason"], "minutes": rec["minutes"], "tool_calls": rec["tool_calls"],
            "input_tokens": usage.get("input"), "output_tokens": usage.get("output"),
            "problems": "; ".join(rec["problems"])}


def read_results(run_id: str) -> list[dict]:
    path = run_dir(run_id) / "results.csv"
    if not path.exists():
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_results(run_id: str, stage: str, rows: list[dict]) -> None:
    path = run_dir(run_id) / "results.csv"
    keep = [r for r in read_results(run_id) if r["stage"] != stage] + rows
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=RESULT_FIELDS)
    w.writeheader()
    for r in sorted(keep, key=lambda r: (r["stage"], r["instance_id"], int(r["sample"]))):
        w.writerow({k: r.get(k, "") for k in RESULT_FIELDS})
    write_text_atomic(path, buf.getvalue())


def evaluate_stage(run_id: str, stage: str) -> list[dict]:
    """Score every valid attempt of `stage` that has no evaluation of its current patch yet."""
    state = load_state(run_id)
    attempts = stage_attempts(run_id, stage)
    if not attempts:
        die(f"stage {stage} of run {run_id} has no attempts; solve it first")
    pending: dict[int, list] = defaultdict(list)
    for rec, d in attempts:
        if not rec["valid"]:
            continue
        old = read_json(d / "eval.json")
        if old and old.get("patch_sha256") == rec["patch_sha256"] and old.get("resolved") is not None:
            continue
        if not rec["patch_lines"]:
            write_json(d / "eval.json", {"resolved": False, "applied": False, "f2p_pass": 0, "f2p_fail": [],
                                         "p2p_fail": [], "note": "empty patch", "patch_sha256": rec["patch_sha256"],
                                         "evaluated_at": timestamp()})
            continue
        pending[rec["sample"]].append((rec, d))
    for sample, items in sorted(pending.items()):
        results = local_eval(run_id, items) if state.get("backend") == "local" else \
            harness_eval(run_id, stage, sample, items)
        for rec, d in items:
            write_json(d / "eval.json", {**results[rec["instance_id"]], "patch_sha256": rec["patch_sha256"],
                                         "evaluated_at": timestamp()})
    rows = [result_row(rec, read_json(d / "eval.json") if rec["valid"] else None) for rec, d in attempts]
    write_results(run_id, stage, rows)
    scored = [r for r in rows if r["valid"] and r["resolved"] is not None]
    unscored = [f"{r['instance_id']}/s{r['sample']}" for r in rows if r["valid"] and r["resolved"] is None]
    resolved = sum(1 for r in scored if r["resolved"])
    with state_update(run_id) as st:
        st.setdefault("stages", {}).setdefault(stage, {}).update(
            evaluated_at=timestamp(), scored=len(scored), resolved=resolved, unscored=unscored,
            resolve_rate=round(resolved / len(scored), 4) if scored else None)
    log(f"{stage}: {resolved} of {len(scored)} scored attempts resolved")
    if unscored:
        die(f"{stage}: the harness could not evaluate {len(unscored)} patch(es): {', '.join(unscored)}. Leaving them "
            f"out would bias the resolve rate. Fix the cause (the harness logs under {run_dir(run_id) / 'harness'}) "
            f"and run the same command again: evaluated attempts are kept, only these are evaluated again.")
    return rows
