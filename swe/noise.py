"""noise: how often the same task flips between resolved and unresolved across student samples of
iteration 0 (no playbook). Outcomes are binary, so this replaces the judge and student variances of
the OpenSpec loop."""

from __future__ import annotations

from lib.common import log, read_json, run_dir, state_update, timestamp, write_json, write_text_atomic

from .core import iteration_stage
from .evaluate import stage_attempts


def outcomes(run_id: str, stage: str) -> dict[str, dict[int, bool]]:
    """Per task, {sample: resolved} for every valid, scored attempt of `stage`."""
    out: dict[str, dict[int, bool]] = {}
    for rec, d in stage_attempts(run_id, stage):
        ev = read_json(d / "eval.json") if rec["valid"] else None
        if ev and ev.get("resolved") is not None:
            out.setdefault(rec["instance_id"], {})[rec["sample"]] = bool(ev["resolved"])
    return out


def cmd_noise(run_id: str) -> dict | None:
    """None, with a warning, when no task has two scored samples yet."""
    stage = iteration_stage(0)
    multi = {t: v for t, v in outcomes(run_id, stage).items() if len(v) >= 2}
    if not multi:
        log(f"warning: no noise baseline: {stage} has no task with two scored samples (iteration 0 takes "
            f"iteration0_samples students per task)")
        return None
    flips = sorted(t for t, v in multi.items() if len(set(v.values())) > 1)
    samples = sorted({s for v in multi.values() for s in v})
    rates = [round(sum(v[s] for v in multi.values() if s in v) / sum(1 for v in multi.values() if s in v), 4)
             for s in samples]
    resolved = [x for v in multi.values() for x in v.values()]
    result = {"stage": stage, "tasks": len(multi), "flip_rate": round(len(flips) / len(multi), 4), "flipped": flips,
              "resolve_rate_per_sample": rates, "resolve_rate": round(sum(resolved) / len(resolved), 4),
              "always_resolved": sorted(t for t, v in multi.items() if all(v.values())),
              "never_resolved": sorted(t for t, v in multi.items() if not any(v.values())), "measured_at": timestamp()}
    write_json(run_dir(run_id) / "noise.json", result)
    md = ["# Noise baseline", "",
          f"{stage}, no playbook: {result['tasks']} tasks with {len(samples)} student samples each.", "",
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
