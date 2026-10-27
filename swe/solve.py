"""Solve stage: one opencode attempt per task and sample, each in a fresh workspace.

An attempt is invalid, and retried, only when it failed for reasons outside the model (the endpoint
was unreachable, the container failed) or leaked (a web tool got through; egress is blocked by the network, so shell
commands that look like network access are only reported). An attempt still invalid after its
retries stops the run. A timeout, an empty patch or a model that gives up are results: they count
as unresolved, so the resolve rate is not flattered by leaving failures out."""

from __future__ import annotations

import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from lib import opencode_stream as ocs
from lib.common import (die, keep_attempt, load_state, log, prompt, read_json, sha256_bytes, state_update,
                        timestamp, write_json, write_text_atomic)
from lib.opencode_runner import run_opencode

from .core import CFG, attempt_dir, check_inputs, model_for, opencode_bin, opencode_config_json
from .env import DockerExecutor, LocalExecutor, container_name

EMPTY_DIFF = "you have not changed any file of the repository yet"
# Raised by docker and git when a container or workspace cannot start or dies mid-attempt: an
# infrastructure failure of that attempt, retried like one, rather than an error of the stage.
WORKSPACE_ERRORS = (RuntimeError, OSError, subprocess.SubprocessError)
NO_RUN = {"infra_error": None, "nudges": 0, "timed_out": False, "finish_reason": None, "duration_s": 0.0,
          "tool_calls": 0, "usage": {}}
REINSTALL_HINT = ("- The repository is installed into the environment, not linked to this checkout: after changing "
                  "the code, run `python setup.py install` in `{workdir}` before running tests, or the tests use the "
                  "old code.\n")


def task_prompt(task: dict, playbook: str | None, workdir: str) -> str:
    section = ("## Playbook\n\nThe playbook below comes from earlier attempts at other issues of this repository. "
               "Follow it.\n\n" + playbook.strip() + "\n\n") if playbook else ""
    return prompt("swe_task.md", repo=task["repo"], workdir=workdir, test_hint=CFG["repo_hints"].get(task["repo"], ""),
                  reinstall_hint=REINSTALL_HINT.format(workdir=workdir) if task.get("reinstall") else "",
                  playbook=section, problem_statement=task["problem_statement"])


def executor_for(backend: str, run_id: str, stage: str, task: dict, sample: int) -> DockerExecutor | LocalExecutor:
    name = container_name(run_id, stage, task["instance_id"], f"s{sample}")
    if backend == "local":
        return LocalExecutor(Path(task["local_repo"]), Path(CFG["workspace_root"]) / run_id / stage / name,
                             opencode_bin())
    return DockerExecutor(task["image"], name, opencode_bin(), CFG["docker"])


def leak_check(events: list[dict]) -> dict:
    attempts = ocs.network_attempts(ocs.tool_calls(events))
    violations = [a for a in attempts if a["succeeded"] and a["tool"] in ocs.WEB_TOOLS]
    return {"ok": not violations, "violations": violations, "warnings": [a for a in attempts if a not in violations]}


def solve_attempt(run_id: str, backend: str, stage: str, role: str, task: dict, sample: int,
                  playbook: str | None, prov: dict) -> dict:
    out = attempt_dir(run_id, stage, task["instance_id"], sample)
    model = model_for(role)
    oc_cfg = opencode_config_json(role)
    ex = executor_for(backend, run_id, stage, task, sample)
    text = task_prompt(task, playbook, ex.workdir)
    digest = sha256_bytes(text.encode("utf-8"))
    old = read_json(out / "attempt.json")
    if old and old["valid"] and old["prompt_sha256"] == digest and old["model"] == model["id"]:
        return old
    for _ in range(CFG["infra_retries"] + 1):
        if out.exists() and any(out.iterdir()):
            keep_attempt(out)
        try:
            ex.start()
            meta = run_opencode(launch=lambda args: ex.launch(args, oc_cfg), model=model["id"], workdir=ex.workdir,
                                prompt=text, out_dir=out, label="trajectory", timeout_min=CFG["timeouts_min"][role],
                                completion_check=lambda: [] if ex.patch().strip() else [EMPTY_DIFF],
                                max_nudges=CFG["completion_nudges"], kill_agent=ex.kill_agent)
            patch = ex.patch()
        except WORKSPACE_ERRORS as e:
            meta, patch = {**NO_RUN, "infra_error": f"the workspace failed: {str(e)[:300]}"}, ""
        finally:
            ex.stop()
        write_text_atomic(out / "patch.diff", patch)
        leaks = leak_check(ocs.parse(out / "trajectory.jsonl"))
        write_json(out / "guards.json", {"leak": leaks})
        problems = ([f"infrastructure: {meta['infra_error']}"] if meta["infra_error"] else []) + \
            ([f"leak: {v['tool']} {v['input'][:120]}" for v in leaks["violations"]])
        record = {"instance_id": task["instance_id"], "stage": stage, "role": role, "sample": sample,
                  "model": model["id"], "prompt_sha256": digest, "playbook_sha256":
                      sha256_bytes(playbook.encode("utf-8")) if playbook else None,
                  "valid": not problems, "problems": problems, "patch_lines": patch.count("\n"),
                  "patch_sha256": sha256_bytes(patch.encode("utf-8")),
                  "attempts": len(list(out.parent.glob(f"{out.name}.attempt*"))) + 1,
                  "nudges": meta["nudges"], "timed_out": meta["timed_out"], "finish_reason": meta["finish_reason"],
                  "minutes": round(meta["duration_s"] / 60, 1), "tool_calls": meta["tool_calls"],
                  "usage": meta["usage"], "provenance": {**prov, "at": timestamp()}, "finished_at": timestamp()}
        write_json(out / "attempt.json", record)
        log(f"{stage} {task['instance_id']} s{sample}: {'valid' if record['valid'] else 'INVALID'}, "
            f"{record['patch_lines']} patch lines" + (f" ({'; '.join(problems)})" if problems else ""))
        if record["valid"]:
            break
    return record


def solve_stage(run_id: str, stage: str, role: str, task_list: list[dict], samples: int,
                playbook: str | None, allow_drift: bool, playbook_source: str | None = None) -> list[dict]:
    prov = check_inputs(run_id, allow_drift, roles=(role,))
    backend = load_state(run_id)["backend"]
    jobs = [(t, s) for t in task_list for s in range(1, samples + 1)]
    log(f"{stage}: {len(jobs)} attempt(s) by the {role} ({model_for(role)['id']})"
        + (f" with the playbook of {playbook_source}" if playbook_source else ", no playbook"))
    with ThreadPoolExecutor(max_workers=max(1, min(len(jobs), CFG["max_parallel_agents"]))) as pool:
        records = list(pool.map(lambda j: solve_attempt(run_id, backend, stage, role, j[0], j[1], playbook, prov),
                                jobs))
    with state_update(run_id) as st:
        st.setdefault("stages", {})[stage] = {
            "role": role, "samples": samples, "tasks": [t["instance_id"] for t in task_list],
            "playbook": {"source": playbook_source, "sha256": sha256_bytes(playbook.encode("utf-8"))}
            if playbook else None,
            "valid": sum(1 for r in records if r["valid"]), "attempts": len(records), "solved_at": timestamp()}
    require_valid(stage, records)
    return records


def require_valid(stage: str, records: list[dict]) -> None:
    """Stop when an attempt is still invalid after its retries: resolve rates, the noise baseline,
    the synthesizer's view and the held-out comparison would silently leave it out."""
    invalid = [f"{r['instance_id']}/s{r['sample']}: {'; '.join(r['problems'])}" for r in records if not r["valid"]]
    if invalid:
        die(f"{stage}: {len(invalid)} of {len(records)} attempts are still invalid after {CFG['infra_retries']} "
            f"retries:\n  " + "\n  ".join(invalid) + "\nFix the cause (each attempt's attempt.json and "
            "trajectory.stderr.log) and run the same command again: valid attempts are reused, only these are retried.")
