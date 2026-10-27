"""noise: how often the same task flips between resolved and unresolved across student samples of
iteration 0 (no playbook). Outcomes are binary, so this replaces the judge and student variances of
the OpenSpec loop."""

from __future__ import annotations

from lib.common import die, log, read_json, run_dir, state_update, timestamp, write_json, write_text_atomic

from .core import iteration_stage
from .evaluate import stage_attempts


def outcomes(run_id: str, stage: str) -> dict[str, list[bool]]:
    """Per task, the resolved flag of every valid, scored attempt of `stage`."""
    out: dict[str, list[bool]] = {}
    for rec, d in stage_attempts(run_id, stage):
        ev = read_json(d / "eval.json") if rec["valid"] else None
        if ev and ev.get("resolved") is not None:
            out.setdefault(rec["instance_id"], []).append(bool(ev["resolved"]))
    return out


def cmd_noise(run_id: str) -> dict:
    stage = iteration_stage(0)
    per_task = outcomes(run_id, stage)
    multi = {t: v for t, v in per_task.items() if len(v) >= 2}
    if not multi:
        die(f"{stage} has no task with two scored samples; run `iterate` (iteration 0 takes "
            f"iteration0_samples students per task) first")
    flips = sorted(t for t, v in multi.items() if len(set(v)) > 1)
    n_samples = max(len(v) for v in multi.values())
    rates = [round(sum(v[i] for v in multi.values() if len(v) > i) / sum(1 for v in multi.values() if len(v) > i), 4)
             for i in range(n_samples)]
    attempts = [x for v in per_task.values() for x in v]
    result = {"stage": stage, "tasks": len(multi), "flip_rate": round(len(flips) / len(multi), 4), "flipped": flips,
              "resolve_rate_per_sample": rates, "resolve_rate": round(sum(attempts) / len(attempts), 4),
              "always_resolved": sorted(t for t, v in multi.items() if all(v)),
              "never_resolved": sorted(t for t, v in multi.items() if not any(v)), "measured_at": timestamp()}
    write_json(run_dir(run_id) / "noise.json", result)
    md = ["# Noise baseline", "",
          f"{stage}, no playbook: {result['tasks']} tasks with {n_samples} student samples each.", "",
          f"- resolve rate per sample: {', '.join(f'{r:.0%}' for r in rates)} (overall {result['resolve_rate']:.0%})",
          f"- tasks whose outcome flips between samples: {len(flips)} of {len(multi)} "
          f"({result['flip_rate']:.0%}): {', '.join(flips) or 'none'}",
          f"- resolved in every sample: {len(result['always_resolved'])}; in none: {len(result['never_resolved'])}",
          "",
          "With one sample per task and arm, about flip rate x tasks of the discordant pairs in a paired comparison "
          "come from sampling alone. Only a difference well beyond that says something about the playbook."]
    write_text_atomic(run_dir(run_id) / "noise.md", "\n".join(md) + "\n")
    with state_update(run_id) as st:
        st["noise"] = {k: result[k] for k in ("tasks", "flip_rate", "resolve_rate", "resolve_rate_per_sample")}
    log(f"noise: {len(flips)} of {len(multi)} tasks flip between samples; resolve rate per sample "
        f"{', '.join(f'{r:.0%}' for r in rates)}")
    return result
