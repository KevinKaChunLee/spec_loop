"""Configuration, run paths, task records, locked inputs and the served-model check of the SWE-bench
loop."""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from lib.common import ROOT, die, log, read_json, run_dir, sha256_bytes, sha256_file, state_update, timestamp, \
    write_json
from lib.opencode_runner import opencode_config, opencode_version

CFG = json.loads((ROOT / "swe_config.json").read_text(encoding="utf-8"))
CFG["workspace_root"] = os.path.expanduser(CFG["workspace_root"])
ROLES = ("oracle", "synthesizer", "student")
# Config keys (dotted paths) that change how a run is operated or how long it is, not what an
# attempt's result means; they may change during a run without counting as drift.
OPERATIONAL_KEYS = ("workspace_root", "python", "max_parallel_agents", "model_notes", "server", "iterations",
                    "iteration0_samples", "test_samples", "harness.max_workers", "docker.network",
                    *(f"models.{r}.base_url" for r in ROLES))
# From SGLang's /server_info: a server relaunched with different values serves a different model.
SERVER_INFO_KEYS = ("version", "model_path", "tool_call_parser", "reasoning_parser", "context_length",
                    "json_model_override_args", "dtype", "quantization", "kv_cache_dtype")
PROMPT_FILES = ("prompts/swe_task.md", "prompts/swe_synthesize.md", "prompts/swe_playbook_rules.md")
# tasks.json is what agents may see; dataset.json holds the full rows (gold patch, tests) for the
# harness, the synthesizer and the leak check.
RUN_FILES = ("tasks.json", "dataset.json")


def json_digest(obj) -> str:
    return sha256_bytes(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8"))


def as_list(value) -> list:
    """FAIL_TO_PASS and PASS_TO_PASS are JSON strings in SWE-bench rows."""
    return json.loads(value) if isinstance(value, str) else list(value or [])


def model_for(role: str) -> dict:
    return CFG["models"][role]


def base_url(role: str) -> str:
    """The OpenAI-compatible endpoint serving `role`'s model: models.<role>.base_url, else
    server.base_url (an SGLang server serves one model, so two models mean two ports)."""
    return (model_for(role).get("base_url") or CFG["server"]["base_url"]).rstrip("/")


def api_key() -> str:
    return os.environ.get(CFG["server"].get("api_key_env") or "", "") or "none"


def opencode_config_json(role: str) -> str:
    return json.dumps(opencode_config(base_url(role), model_for(role), api_key()), separators=(",", ":"))


def opencode_bin() -> str:
    """The opencode binary as an absolute path (it is mounted into containers by path)."""
    found = shutil.which(os.path.expanduser(CFG["opencode"]["bin"]))
    if not found:
        die(f"opencode not found: {CFG['opencode']['bin']} (set opencode.bin in swe_config.json)")
    return os.path.realpath(found)


def stage_dir(run_id: str, stage: str) -> Path:
    return run_dir(run_id) / stage


def attempt_dir(run_id: str, stage: str, iid: str, sample: int) -> Path:
    return stage_dir(run_id, stage) / iid / f"s{sample}"


def playbook_path(run_id: str, stage: str) -> Path:
    """The playbook written from `stage`'s attempts (used by the next iteration)."""
    return stage_dir(run_id, stage) / "playbook" / "playbook.md"


def iteration_stage(k: int) -> str:
    return f"iter-{k:02d}"


def tasks(run_id: str, split: str) -> list[dict]:
    return read_json(run_dir(run_id) / "tasks.json", {}).get(split, [])


def gold(run_id: str, iid: str) -> dict:
    """The gold patch, test patch and test lists of a task: never for a solving agent."""
    row = next((r for r in read_json(run_dir(run_id) / "dataset.json", []) if r["instance_id"] == iid), None)
    if row is None:
        die(f"{iid} is not in {run_dir(run_id) / 'dataset.json'}; prepare the run again")
    return {"patch": row.get("patch") or "", "test_patch": row.get("test_patch") or "",
            "FAIL_TO_PASS": as_list(row.get("FAIL_TO_PASS")), "PASS_TO_PASS": as_list(row.get("PASS_TO_PASS"))}


def swebench_version() -> str:
    try:
        return subprocess.run([CFG["python"], "-c", "import swebench; print(swebench.__version__)"],
                              capture_output=True, text=True, timeout=120).stdout.strip() or "unknown"
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"


def _get_json(url: str, timeout: float = 15) -> dict | None:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key()}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except (urllib.error.URLError, OSError, ValueError):
        return None


def endpoint(base: str) -> dict | None:
    """What one endpoint serves now, or None when it cannot be reached: {"models": {id: {root,
    max_model_len}}, "server": the SGLang version and the launch arguments that change results}."""
    models = _get_json(f"{base}/models")
    if models is None:
        return None
    root = base[: -len("/v1")] if base.endswith("/v1") else base
    info = _get_json(f"{root}/server_info") or _get_json(f"{root}/get_server_info") or {}
    return {"models": {m.get("id"): {"root": m.get("root"), "max_model_len": m.get("max_model_len")}
                       for m in models.get("data", [])},
            "server": {k: info.get(k) for k in SERVER_INFO_KEYS}}


def served_models(roles: tuple[str, ...] = ROLES) -> dict[str, dict | None]:
    """{base_url: what it serves, or None} for the endpoints of `roles`."""
    return {base: endpoint(base) for base in sorted({base_url(r) for r in roles})}


def served_by_role(served: dict[str, dict | None], roles: tuple[str, ...]) -> dict[str, dict | None]:
    """What serves each role's model, without the URL (a moved server is not a different model)."""
    out = {}
    for r in roles:
        s = served.get(base_url(r))
        m = (s or {}).get("models", {}).get(model_for(r)["id"])
        out[r] = None if m is None else {"model": model_for(r)["id"], **m, **s["server"]}
    return out


def require_models(served: dict[str, dict | None], roles: tuple[str, ...]) -> None:
    for r in roles:
        base, mid = base_url(r), model_for(r)["id"]
        if served.get(base) is None:
            die(f"the {r} model's endpoint {base} cannot be reached; start its SGLang server or fix its base_url "
                f"in swe_config.json (`swe_loop.py check` tests it)")
        if mid not in served[base]["models"]:
            die(f"{base} does not serve the {r} model {mid} (it serves {', '.join(served[base]['models'])})")


def current_inputs() -> dict:
    cfg = copy.deepcopy(CFG)
    for key in OPERATIONAL_KEYS:
        *parents, last = key.split(".")
        node = cfg
        for p in parents:
            node = node.get(p, {})
        node.pop(last, None)
    return {"config": json_digest(cfg),
            "prompts": {p: sha256_file(ROOT / p) for p in PROMPT_FILES},
            "opencode": opencode_version(opencode_bin()), "swebench": swebench_version()}


def write_lock(run_id: str, served: dict[str, dict | None]) -> None:
    write_json(run_dir(run_id) / "inputs.lock.json",
               {"created": timestamp(), **current_inputs(), "served": served_by_role(served, ROLES),
                "run_files": {f: sha256_file(run_dir(run_id) / f) for f in RUN_FILES}})


def check_inputs(run_id: str, allow_drift: bool, roles: tuple[str, ...]) -> dict:
    """Compare the current inputs, and what serves the models of `roles`, with inputs.lock.json;
    die on a difference unless `allow_drift`. Returns the provenance to stamp into this stage's
    attempts: a digest of the current inputs and what serves each role."""
    lock_path = run_dir(run_id) / "inputs.lock.json"
    lock = read_json(lock_path, {})
    cur = current_inputs()
    drift = []
    if lock.get("config") != cur["config"]:
        drift.append("swe_config.json changed")
    drift += [f"{p} changed" for p, d in lock.get("prompts", {}).items() if cur["prompts"].get(p) != d]
    for key in ("opencode", "swebench"):
        if lock.get(key) not in (None, "unknown") and cur[key] != "unknown" and lock[key] != cur[key]:
            drift.append(f"{key} {lock[key]} -> {cur[key]}")
    drift += [f"{f} changed" for f, d in lock.get("run_files", {}).items() if sha256_file(run_dir(run_id) / f) != d]
    served = served_models(roles)
    require_models(served, roles)
    by_role = served_by_role(served, roles)
    recorded = lock.get("served") or {}
    new = {r: s for r, s in by_role.items() if recorded.get(r) is None}
    if new:
        lock["served"] = recorded | new
        write_json(lock_path, lock)
        log("recorded the served models in inputs.lock.json: " + "; ".join(
            f"{r}: {s['model']} (SGLang {s['version']}, context {s['max_model_len']})" for r, s in new.items()))
    drift += [f"the {r} model's server changed: {recorded[r]} -> {s}"
              for r, s in by_role.items() if r not in new and recorded[r] != s]
    if drift:
        msg = "inputs changed since prepare: " + "; ".join(drift)
        if not allow_drift:
            die(f"{msg}. Results from here on would not be comparable with the run's earlier ones: restore the "
                f"inputs, prepare a new run, or pass --allow-drift (recorded in state.json)")
        log(f"warning: {msg} (--allow-drift; recorded in state.json)")
        with state_update(run_id) as state:
            if (state.get("drift") or [{}])[-1].get("changed") != drift:
                state.setdefault("drift", []).append({"at": timestamp(), "changed": drift})
    return {"inputs": json_digest({k: cur[k] for k in ("config", "prompts", "opencode", "swebench")}),
            "served": by_role}
