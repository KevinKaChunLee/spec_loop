"""Solve stage: one opencode attempt per task and sample, each in a fresh workspace.

An attempt is invalid, and retried, only when it failed for reasons outside the model (the endpoint
was unreachable) or leaked (a web tool or a network command got through). A timeout, an empty patch
or a model that gives up are results: they count as unresolved, so the resolve rate is not
flattered by leaving failures out."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from lib import opencode_stream as ocs
from lib.common import (load_state, log, prompt, read_json, sha256_bytes, state_update, timestamp, write_json,
                        write_text_atomic)
from lib.opencode_runner import opencode_config, run_opencode

from .core import CFG, api_key, attempt_dir, base_url, check_inputs, model_for, opencode_bin, provenance
from .env import DockerExecutor, LocalExecutor, config_json

EMPTY_DIFF = "you have not changed any file of the repository yet"
REINSTALL_HINT = ("- The repository is installed into the environment, not linked to this checkout: after changing "
                  "the code, run `python setup.py install` in `{workdir}` before running tests, or the tests use the "
                  "old code.\n")


def task_prompt(task: dict, playbook: str | None, workdir: str) -> str:
    section = ("## Playbook\n\nThe playbook below comes from earlier attempts at other issues of this repository. "
               "Follow it.\n\n" + playbook.strip() + "\n\n") if playbook else ""
    return prompt("swe_task.md", repo=task["repo"], workdir=workdir, test_hint=CFG["repo_hints"].get(task["repo"], ""),
                  reinstall_hint=REINSTALL_HINT.format(workdir=workdir) if task.get("reinstall") else "",
                  playbook=section, problem_statement=task["problem_statement"])


def executor_for(state: dict, run_id: str, stage: str, task: dict, sample: int):
    name = re.sub(r"[^a-zA-Z0-9_.-]", "-", f"swe-{run_id}-{stage}-{task['instance_id']}-s{sample}")
    if state.get("backend") == "local":
        return LocalExecutor(Path(task["local_repo"]), Path(CFG["workspace_root"]) / run_id / stage / name,
                             opencode_bin())
    return DockerExecutor(task["image"], name, opencode_bin(), CFG["docker"],
                          conda_activate=CFG["docker"]["conda_activate"])


def keep_attempt(out: Path) -> None:
    n = 1
    while out.with_name(f"{out.name}.attempt{n}").exists():
        n += 1
    out.rename(out.with_name(f"{out.name}.attempt{n}"))


def leak_check(events: list[dict]) -> dict:
    attempts = ocs.network_attempts(ocs.tool_calls(events))
    return {"ok": not any(a["succeeded"] for a in attempts),
            "violations": [a for a in attempts if a["succeeded"]],
            "warnings": [a for a in attempts if not a["succeeded"]]}


def solve_attempt(run_id: str, state: dict, stage: str, role: str, task: dict, sample: int,
                  playbook: str | None, served: dict) -> dict:
    out = attempt_dir(run_id, stage, task["instance_id"], sample)
    model = model_for(role)
    oc_cfg = config_json(opencode_config(base_url(role), [model], model["id"], api_key()))
    old = read_json(out / "attempt.json")
    for attempt in range(CFG["infra_retries"] + 1):
        ex = executor_for(state, run_id, stage, task, sample)
        text = task_prompt(task, playbook, ex.workdir)
        digest = sha256_bytes(text.encode("utf-8"))
        if old and old.get("valid") and old.get("prompt_sha256") == digest and old.get("model") == model["id"]:
            return old
        if out.exists() and any(out.iterdir()):
            keep_attempt(out)
        ex.start()
        try:
            meta = run_opencode(launch=lambda args: ex.launch(args, oc_cfg), model=model["id"], workdir=ex.workdir,
                                prompt=text, out_dir=out, label="trajectory", timeout_min=CFG["timeouts_min"][role],
                                completion_check=lambda: [] if ex.patch().strip() else [EMPTY_DIFF],
                                max_nudges=CFG["completion_nudges"], kill_agent=ex.kill_agent)
            patch = ex.patch()
        finally:
            ex.stop()
        write_text_atomic(out / "patch.diff", patch)
        leaks = leak_check(ocs.parse(out / "trajectory.jsonl"))
        write_json(out / "guards.json", {"leak": leaks})
        problems = ([f"infrastructure: {meta['infra_error']}"] if meta["infra_error"] else []) + \
            ([f"leak: {v['tool']} {v['input'][:120]}" for v in leaks["violations"]])
        earlier = sorted(out.parent.glob(f"{out.name}.attempt*"))
        record = {"instance_id": task["instance_id"], "stage": stage, "role": role, "sample": sample,
                  "model": model["id"], "prompt_sha256": digest, "playbook_sha256":
                      sha256_bytes(playbook.encode("utf-8")) if playbook else None,
                  "valid": not problems, "problems": problems, "patch_lines": patch.count("\n"),
                  "patch_sha256": sha256_bytes(patch.encode("utf-8")), "attempts": len(earlier) + 1,
                  "nudges": meta["nudges"], "timed_out": meta["timed_out"], "finish_reason": meta["finish_reason"],
                  "minutes": round(meta["duration_s"] / 60, 1), "tool_calls": meta["tool_calls"],
                  "usage": meta["usage"], "provenance": provenance(run_id, served), "finished_at": timestamp()}
        write_json(out / "attempt.json", record)
        log(f"{stage} {task['instance_id']} s{sample}: {'valid' if record['valid'] else 'INVALID'}, "
            f"{record['patch_lines']} patch lines" + (f" ({'; '.join(problems)})" if problems else ""))
        if record["valid"]:
            return record
        old = None
    return record


def solve_stage(run_id: str, stage: str, role: str, task_list: list[dict], samples: int,
                playbook: str | None, allow_drift: bool, playbook_source: str | None = None) -> list[dict]:
    served = check_inputs(run_id, allow_drift, roles=(role,))
    state = load_state(run_id)
    jobs = [(t, s) for t in task_list for s in range(1, samples + 1)]
    log(f"{stage}: {len(jobs)} attempt(s) by the {role} ({model_for(role)['id']})"
        + (f" with the playbook of {playbook_source}" if playbook_source else ", no playbook"))
    with ThreadPoolExecutor(max_workers=max(1, min(len(jobs), CFG["max_parallel_agents"]))) as pool:
        records = list(pool.map(lambda j: solve_attempt(run_id, state, stage, role, j[0], j[1], playbook, served), jobs))
    with state_update(run_id) as st:
        st.setdefault("stages", {})[stage] = {
            "role": role, "samples": samples, "tasks": [t["instance_id"] for t in task_list],
            "playbook": {"source": playbook_source, "sha256": records[0]["playbook_sha256"]} if playbook else None,
            "valid": sum(1 for r in records if r["valid"]), "attempts": len(records), "solved_at": timestamp()}
    return records
