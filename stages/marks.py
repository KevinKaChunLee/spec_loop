"""Iteration scores: which samples count, noise thresholds, marks and gap ids."""

from __future__ import annotations

import math

from pathlib import Path

from lib.common import log, read_json, run_dir

from .core import iteration_samples, key_label, read_csv, student_valid, write_csv


def iteration_scores(state: dict) -> dict[int, float]:
    return {int(j): v["score"] for j, v in state["iters"].items() if v.get("score") is not None}


def scored_count(it: dict) -> int:
    return sum(1 for r in it.get("compare", []) if r.get("ok"))


def mean_score_variance(var_student: float, var_judge: float, n: int, judges: int) -> float:
    """Variance of the mean of n samples with `judges` judge passes each."""
    return var_student / n + var_judge / (n * judges)


def score_variance(state: dict, k: int) -> float | None:
    """Variance of iteration k's score from the noise baseline; None without one. A baseline
    measured before the variances were recorded used another student variance and gives none
    either, until `noise` is run again."""
    noise, it = state.get("noise"), state["iters"].get(str(k), {})
    n = scored_count(it)
    if not noise or "var_student" not in noise or not n:
        return None
    return mean_score_variance(noise["var_student"], noise["var_judge"], n, it.get("judges") or 1)


def significance_threshold(var_a: float, var_b: float) -> float:
    """Two scores differ significantly when they differ by more than 2 sqrt(var_a + var_b)."""
    return round(2 * math.sqrt(var_a + var_b), 1)


def pair_threshold(state: dict, a: int, b: int) -> float | None:
    va, vb = score_variance(state, a), score_variance(state, b)
    return None if va is None or vb is None else significance_threshold(va, vb)


def change_vs_best(state: dict, k: int) -> dict | None:
    """Iteration k's score against the best earlier iteration, marked against the noise threshold
    for that pair of iterations."""
    scores = iteration_scores(state)
    earlier = {j: s for j, s in scores.items() if j < k}
    if k not in scores or not earlier:
        return None
    best = max(earlier, key=lambda j: (earlier[j], j))
    delta = round(scores[k] - earlier[best], 1)
    threshold = pair_threshold(state, k, best)
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


def scored_samples(run_id: str, state: dict, k: int) -> list[tuple[str, Path, Path, dict]]:
    """(label, student dir, compare dir, score) of the samples of iteration k that count: a valid
    student run with a score.json, from the latest comparison when state.json records one."""
    ok = None
    if state["iters"].get(str(k), {}).get("compare"):
        ok = {key_label(r["sample"]) for r in state["iters"][str(k)]["compare"] if r.get("ok")}
    out = []
    for label, s, c in iteration_samples(run_id, k):
        if (ok is None or label in ok) and student_valid(s) and (c / "score.json").exists():
            out.append((label, s, c, read_json(c / "score.json")))
    return out


def iteration_gaps(run_id: str, state: dict, k: int) -> set[str] | None:
    scores = [sc for _l, _s, _c, sc in scored_samples(run_id, state, k)]
    return majority_gaps(scores) if scores else None


def mark_iteration(run_id: str, state: dict, k: int) -> None:
    """Fill vs_best, gaps_closed and gaps_reopened in the scores.csv rows of iteration k."""
    change = change_vs_best(state, k)
    prev = iteration_gaps(run_id, state, k - 1) if k > 0 else None
    earlier: set[str] = set()
    for j in range(k - 1):
        earlier |= iteration_gaps(run_id, state, j) or set()
    csv_path = run_dir(run_id) / "scores.csv"
    rows = read_csv(csv_path)
    scores = {label: sc for label, _s, _c, sc in scored_samples(run_id, state, k)}
    for r in rows:
        if r["iter"] != str(k):
            continue
        r["vs_best"] = (f"{change['delta']:+.1f}" + (f" {change['mark']}" if change["mark"] else "")) if change else ""
        ids = stable_gap_ids(scores.get(key_label(r["sample"]), {}))
        if prev is not None:
            r["gaps_closed"] = len(prev - ids)
            r["gaps_reopened"] = len((ids - prev) & earlier)
    write_csv(csv_path, rows)
    if change:
        log(f"iteration {k}: score {iteration_scores(state)[k]}, {change['delta']:+.1f} vs the best earlier "
            f"iteration {change['best_iter']} ({change['best']})"
            + (f": {change['mark']} (threshold {change['threshold']})" if change["mark"] else
               " (no noise threshold measured yet)"))


def best_playbook_iter(state: dict) -> int | None:
    """Iteration with the highest raw score among those that used a playbook (k >= 1)."""
    scores = {j: s for j, s in iteration_scores(state).items() if j >= 1}
    return max(scores, key=lambda j: (scores[j], j)) if scores else None
