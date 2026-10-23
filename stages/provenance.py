"""What a run and its scores depend on: the locked inputs, drift checks and provenance stamps."""

from __future__ import annotations

import functools
import json

from pathlib import Path

from lib.common import (PROMPTS, ROOT, die, load_state, log, read_json, run_dir, sha256_bytes, state_update,
                        sha256_file, timestamp)
from lib.runner import cli_version, tool_version

from .core import CFG, manifest_text, oracle_dir, smoke, task_file


# Config keys that change how a run is operated, not what its scores mean.
OPERATIONAL_KEYS = ("iterations", "judges", "max_parallel_agents", "model_notes", "workspace_root")
# Hashed once, at import: a stamp must describe the code this process runs, even if the files are
# edited during a long run.
SCORING_CODE_SHA = sha256_bytes(b"".join((ROOT / p).read_bytes()
                                         for p in ("stages/scoring.py", "lib/decisions.py", "lib/spec_metrics.py")))
# What the extractor reads besides the spec and the task.
EXTRACTION_INPUTS = ("decision_vocab.json", "prompts/extract.md")


def json_digest(obj) -> str:
    return sha256_bytes(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8"))


def file_hashes(paths) -> dict[str, str]:
    """sha256 of files given relative to spec_loop/."""
    return {p: sha256_file(ROOT / p) for p in paths}


def changed_files(recorded: dict[str, str]) -> list[str]:
    """Recorded files (relative to spec_loop/) that are gone or differ from their recorded hash."""
    return [p for p, d in recorded.items() if not (ROOT / p).exists() or sha256_file(ROOT / p) != d]


def prompt_files() -> list[str]:
    return ["rubric.md", "decision_vocab.json", *[f"prompts/{p.name}" for p in sorted(PROMPTS.glob("*.md"))]]


def config_fingerprint() -> str:
    return json_digest({k: v for k, v in CFG.items() if k not in OPERATIONAL_KEYS})


def skill_hashes() -> dict[str, str]:
    return {p.parent.name: sha256_file(p)
            for p in sorted(Path(CFG["cursor_dir"]).glob("skills/openspec-*/SKILL.md"))}


@functools.cache
def openspec_version() -> str:
    return tool_version(["openspec", "--version"])


def current_inputs(smoke_run: bool) -> dict:
    """Everything besides the run's own data that a score depends on."""
    return {"prompts": file_hashes(prompt_files()), "config": config_fingerprint(),
            "skills": skill_hashes(), "models": {"smoke": CFG["smoke_model"]} if smoke_run else CFG["models"],
            "agent_cli": cli_version(), "openspec_cli": openspec_version()}


def input_drift(run_id: str, state: dict) -> list[str]:
    """How the current inputs differ from inputs.lock.json."""
    lock = read_json(run_dir(run_id) / "inputs.lock.json", {})
    cur = current_inputs(smoke(state))
    locked = lock.get("prompts", {})
    out = [f"{p} changed" for p, d in locked.items() if cur["prompts"].get(p, d) != d]
    out += [f"{p} is new" for p in cur["prompts"] if p not in locked]
    out += [f"{p} was deleted" for p in locked if p not in cur["prompts"]]
    if "config_fingerprint" in lock:
        if lock["config_fingerprint"] != cur["config"]:
            out.append(f"config.json changed (beyond {', '.join(OPERATIONAL_KEYS)})")
    elif lock.get("config") and lock["config"] != sha256_file(ROOT / "config.json"):
        out.append("config.json changed")
    skills = lock.get("skills", {})
    out += [f"skill {n} changed" for n, d in skills.items() if cur["skills"].get(n) != d]
    out += [f"skill {n} is new" for n in cur["skills"] if n not in skills]
    if lock.get("models") and lock["models"] != cur["models"]:
        out.append("models changed")
    for key, label in (("agent_cli", "agent CLI"), ("openspec_cli", "openspec CLI")):
        if lock.get(key) not in (None, "unknown") and cur[key] != "unknown" and lock[key] != cur[key]:
            out.append(f"{label} {lock[key]} -> {cur[key]}")
    return out


def check_inputs_unchanged(run_id: str, allow_drift: bool) -> None:
    state = load_state(run_id)
    drift = input_drift(run_id, state)
    if not drift:
        return
    msg = "inputs changed since prepare: " + "; ".join(drift)
    if not allow_drift:
        die(f"{msg}. Scores from here on would not be comparable with the run's earlier ones: restore the "
            f"inputs, prepare a new run, or pass --allow-drift to continue anyway (recorded in state.json)")
    log(f"warning: {msg} (--allow-drift; recorded in state.json)")
    with state_update(run_id) as state:
        if (state.get("drift") or [{}])[-1].get("changed") != drift:
            state.setdefault("drift", []).append({"at": timestamp(), "changed": drift})


def reference_inputs(state: dict) -> tuple[str, ...]:
    """The files the reference decisions were extracted under."""
    return *EXTRACTION_INPUTS, f"prompts/{task_file(state)}"


def reference_drift(src: str, src_state: dict) -> list[str]:
    """How the current vocabulary, extraction prompt and task differ from those the source run's
    reference decisions were extracted under (recorded at freeze; older runs only have the
    inputs.lock.json written at prepare, before the extraction, of the run that extracted them)."""
    rdec = src_state.get("reference_decisions", {})
    under = rdec.get("extracted_under")
    if not under and rdec.get("copied_from"):
        return reference_drift(rdec["copied_from"], load_state(rdec["copied_from"]))
    note = ""
    if not under:
        under = read_json(run_dir(src) / "inputs.lock.json", {}).get("prompts", {})
        note = f" (from {src}'s inputs.lock.json, written at prepare)"
    names = reference_inputs(src_state)
    return ([f"{p} not recorded{note}" for p in names if p not in under] +
            [f"{p} changed{note}" for p in changed_files({p: under[p] for p in names if p in under})])


def spec_digest(spec_root: Path) -> str:
    return sha256_bytes(manifest_text(spec_root).encode("utf-8"))


def score_provenance(run_id: str, state: dict, stu_dir: Path, judges: int) -> dict:
    """What a score.json is produced from; reuse_mode compares it to decide whether the score can
    be reused as it is, recomputed from its saved model outputs, or must be judged again."""
    return {"inputs": current_inputs(smoke(state)), "student_spec": spec_digest(stu_dir / "spec"),
            "reference": sha256_file(oracle_dir(run_id) / "MANIFEST.sha256"), "judges": judges,
            "scoring_code": SCORING_CODE_SHA}


def reuse_mode(old: dict | None, new: dict) -> str:
    """`same`: reuse the score as it is; `aggregate`: the model outputs are reusable but the scoring
    code changed; `legacy`: the score predates provenance stamps; `none`: score again."""
    if not old:
        return "none"
    prov = old.get("provenance")
    if prov is None:
        return "legacy"
    if any(prov.get(k) != new[k] for k in ("inputs", "student_spec", "reference", "judges")):
        return "none"
    return "same" if prov.get("scoring_code") == new["scoring_code"] else "aggregate"
