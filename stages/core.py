"""Configuration, run paths, models, sample directories and small helpers shared by every stage."""

from __future__ import annotations

import csv
import io
import re
import statistics

from pathlib import Path

from lib import decisions as dec
from lib import spec_metrics
from lib.common import die, iter_dir, load_config, log, prompt, read_json, run_dir, sha256_file, write_text_atomic


CFG = load_config()
SCORING = CFG["scoring"]
DIMENSIONS = list(SCORING["weights"])


DECISIONS_FILE = "decisions.json"
# How the reference was formed from the oracles: votes, contested keys, coverage names, medoid.
CONSENSUS_FILE = "consensus.json"
SMOKE_ORACLES = 2
CSV_FIELDS = ["iter", "sample", "total", "vs_best", *DIMENSIONS, "judges", "judge_spread", "code_share",
              "disputes", "gaps_student_wrong", "gaps_high", "gaps_closed", "gaps_reopened", "validate_ok",
              "leak_ok", "no_code_ok", "hmos_coverage", "subagents", "nudges", "attempts", "input_tokens",
              "output_tokens", "duration_min", "model"]


def smoke(state: dict) -> bool:
    return bool(state.get("smoke"))


def model_for(state: dict, role: str) -> dict:
    return CFG["smoke_model"] if smoke(state) else CFG["models"][role]


def timeout_for(state: dict, role: str) -> float:
    return CFG["timeouts_min"]["smoke"] if smoke(state) else CFG["timeouts_min"][role]


def task_file(state: dict) -> str:
    return "smoke_task.md" if smoke(state) else "task.md"


def task_text(state: dict) -> str:
    return prompt(task_file(state), change_name=CFG["change_name"])


def base_dir(run_id: str) -> Path:
    return run_dir(run_id) / "base"


def hmos_index(run_id: str) -> dict:
    return spec_metrics.build_hmos_index(base_dir(run_id), CFG["hmos_dir"],
                                         run_dir(run_id) / "hmos_index.json")


def oracle_dir(run_id: str) -> Path:
    return run_dir(run_id) / "oracle"


def oracle_spec(run_id: str) -> Path:
    """The reference spec (for a reference formed by consensus, the medoid oracle's, copied here)."""
    return oracle_dir(run_id) / "spec"


def oracle_runs(run_id: str, state: dict) -> list[tuple[str, Path]]:
    """(label, directory) of each independent oracle: o1, o2, ..."""
    n = SMOKE_ORACLES if smoke(state) else CFG["oracle_samples"]
    return [(f"o{i}", oracle_dir(run_id) / f"o{i}") for i in range(1, n + 1)]


def shared_idents(run_id: str, state: dict) -> set[str]:
    """Identifiers AGENTS.md, config.yaml and the task already give, left out of coverage."""
    base = base_dir(run_id)
    texts = [(base / rel).read_text(encoding="utf-8", errors="replace")
             for rel in ("AGENTS.md", "openspec/config.yaml") if (base / rel).exists()]
    return dec.allowed_symbols([*texts, task_text(state)])[0]


def reference_names(run_id: str, index: dict, shared: set[str]) -> set[str]:
    """The behaviour-coverage target: the HMOS names a majority of the oracles cite, or for a
    reference frozen from a single oracle (no consensus.json), the names its spec cites."""
    consensus = read_json(oracle_dir(run_id) / CONSENSUS_FILE)
    if consensus is not None:
        return set(consensus["names"])
    return dec.cited_names(oracle_spec(run_id), CFG, index, shared)


def manifest_text(spec_root: Path) -> str:
    lines = [f"{sha256_file(p)}  {p.relative_to(spec_root).as_posix()}"
             for p in sorted(spec_root.rglob("*")) if p.is_file()]
    return "\n".join(lines) + "\n"


def manifest_expected(run_id: str, state: dict) -> str:
    """MANIFEST.sha256: the frozen spec files, then the frozen reference decisions and, for a
    reference formed by consensus, consensus.json."""
    text = manifest_text(oracle_spec(run_id))
    if state.get("reference_decisions", {}).get("frozen"):
        text += f"{sha256_file(oracle_dir(run_id) / DECISIONS_FILE)}  {DECISIONS_FILE}\n"
        if (oracle_dir(run_id) / CONSENSUS_FILE).exists():
            text += f"{sha256_file(oracle_dir(run_id) / CONSENSUS_FILE)}  {CONSENSUS_FILE}\n"
    return text


def verify_frozen(run_id: str, state: dict) -> None:
    if not state.get("frozen"):
        die("the reference is not frozen yet; run `loop.py oracle` (it freezes the reference once every "
            "oracle is valid)")
    manifest = oracle_dir(run_id) / "MANIFEST.sha256"
    if manifest_expected(run_id, state) != manifest.read_text(encoding="utf-8"):
        die(f"the frozen oracle spec or reference decisions changed since freeze ({manifest}); "
            f"restore them before continuing")


def reference_decisions(run_id: str, state: dict, required: bool = True) -> dict | None:
    frozen = oracle_dir(run_id) / DECISIONS_FILE
    if state.get("reference_decisions", {}).get("frozen") and frozen.exists():
        return read_json(frozen)
    if required:
        die(f"run '{run_id}' has a frozen spec but no reference decisions (it predates them); prepare a new run"
            if state.get("frozen") else
            f"the reference decisions of run '{run_id}' are not frozen: run `loop.py oracle --run {run_id}`")
    return None


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
    write_text_atomic(path, buf.getvalue())


def sample_label(state: dict, sample: int, samples: int) -> str:
    """Directory suffix of a sample: runs prepared since the `-sN` naming always use `-sN`; older
    runs (r1) used no suffix for a single sample."""
    return f"-s{sample}" if state.get("naming") == "sN" or samples > 1 else ""


def key_label(key: str) -> str:
    """The iteration_samples label of a sample as state.json and scores.csv name it ("-" is r1's
    plain student/, read as s1)."""
    return key.lstrip("-") or "s1"


def iteration_samples(run_id: str, k: int) -> list[tuple[str, Path, Path]]:
    """(label, student dir, compare dir) of every sample of an iteration; a plain `student`
    directory (r1) reads as s1."""
    it = iter_dir(run_id, k)
    out = []
    for d in sorted(it.glob("student*"), key=lambda p: (len(p.name), p.name)):
        sfx = d.name[len("student"):]
        if d.is_dir() and (sfx == "" or re.fullmatch(r"-s\d+", sfx)):
            out.append((key_label(sfx), d, it / f"compare{sfx}"))
    return out


def score_judges(score: dict) -> int:
    """Judge passes behind a score.json (a single pass records no per-judge list)."""
    return len(score.get("judges", [])) or 1


def reuse_json(path: Path, ok) -> dict | None:
    data = read_json(path)
    if data is not None and ok(data):
        log(f"reusing {path}")
        return data
    return None


def sd(xs: list[float]) -> float:
    return statistics.stdev(xs) if len(xs) > 1 else 0.0


def dim_points(values: dict[str, float]) -> dict[str, float]:
    return {d: values[d] * SCORING["weights"][d] / sum(SCORING["weights"].values()) * 100 for d in DIMENSIONS}


def student_problems(meta: dict, guards_result: dict) -> list[str]:
    """Why a student run does not count, from its run metadata and its guards result."""
    return [p for p, bad in (("the agent run failed", not meta.get("ok")),
                             ("leak", not guards_result.get("leak", {}).get("ok")),
                             ("deliverables missing", bool(meta.get("incomplete")))) if bad]


def student_valid(stu_dir: Path) -> bool:
    return (stu_dir / "spec" / "openspec").is_dir() and not student_problems(
        read_json(stu_dir / "trajectory.run.json", {}), read_json(stu_dir / "guards.json", {}))
