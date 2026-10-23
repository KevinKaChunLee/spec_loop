"""noise: the spread between samples, judges and extraction passes of one iteration."""

from __future__ import annotations

import math
import statistics

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from lib import decisions as dec
from lib.common import die, load_state, log, read_json, run_dir, state_update, timestamp, write_json

from .core import (CFG, DIMENSIONS, SCORING, dim_points, hmos_index, iteration_samples, model_for,
                   reference_decisions, reuse_json, score_judges, sd, verify_frozen)
from .provenance import EXTRACTION_INPUTS, check_inputs_unchanged, file_hashes, spec_digest
from .extraction import extract_spec
from .marks import iteration_scores, mark_iteration, mean_score_variance, scored_samples, significance_threshold


def effective_agreement(cmp_dir: Path) -> dict[str, bool]:
    """Per decision item: does it count as agreement (in the table, or by a lenient ruling)."""
    d = read_json(cmp_dir / "decisions_compare.json", {})
    rulings = d.get("rulings", {})
    return {it["id"]: it["status"] == "agree" or rulings.get(it["id"], {}).get("ruling") in dec.COUNTS_AS_AGREEMENT
            for it in d.get("items", [])}


def judge_flips(cmp_dir: Path) -> list[str]:
    by_judge = read_json(cmp_dir / "decisions_compare.json", {}).get("rulings_by_judge") or []
    ids = set().union(*by_judge) if by_judge else set()
    return sorted(i for i in ids if len({r.get(i, {}).get("ruling") for r in by_judge}) > 1)


def extraction_noise(run_id: str, state: dict, samples: list[tuple[str, Path, Path, dict]]) -> dict:
    """A second extraction pass over every sample's spec (kept in compare-sN/decisions-pass2/):
    which decisions the extractor itself reads differently, and how many points that could move
    the sample. The bound counts every item whose agreement status changes; a dispute ruling
    could still absorb some of them."""
    vocab, index, ref = dec.load_vocab(), hmos_index(run_id), reference_decisions(run_id, state)
    under = file_hashes(EXTRACTION_INPUTS)
    points = dec.part_points(SCORING)
    # None: the second extraction failed; {"skipped": True}: no first extraction to compare with.
    per: dict[str, dict | None] = {}
    usable = []
    for sample in samples:
        t1 = read_json(sample[2] / "decisions" / "decisions.json")
        mods = read_json(sample[2] / "decisions_compare.json", {}).get("modules")
        per[sample[0]] = None if t1 is not None and mods else {"skipped": True}
        if t1 is not None and mods:
            usable.append((sample, t1, mods))

    def second(sample):
        label, s, c, _sc = sample
        out = c / "decisions-pass2"
        prov = {"student_spec": spec_digest(s / "spec"), **under, "model": model_for(state, "extractor")}
        old = reuse_json(out / "decisions.json", lambda _d: read_json(out / "provenance.json") == prov)
        if old is not None:
            return old
        table = extract_spec(run_id, state, s / "spec", out, f"noise-extract-{label}",
                             f"noise: second extraction of {label}")
        if table is not None:
            write_json(out / "provenance.json", prov)
        return table

    with ThreadPoolExecutor(max_workers=max(1, len(usable))) as pool:
        seconds = list(pool.map(second, [u[0] for u in usable]))
    differ = set()
    for ((label, _s, _c, _sc), t1, mods), t2 in zip(usable, seconds):
        if t2 is None:
            continue
        ag = dec.extraction_agreement(t1, t2, vocab)
        i1 = dec.compare(ref, t1, mods["reference"], mods["student"], vocab, index)
        i2 = dec.compare(ref, t2, mods["reference"], mods["student"], vocab, index)
        n = Counter(it["group"] for it in i1)
        flips = [a for a, b in zip(i1, i2) if (a["status"] == "agree") != (b["status"] == "agree")]
        per[label] = {"agreement": ag["agreement"], "stated_agreement": ag["stated_agreement"],
                      "keys_that_differ": [d["id"] for d in ag["diffs"]],
                      "agreement_flips": [a["id"] for a in flips],
                      "points_bound": round(sum(points[dec.GROUP_PART[a["group"]]] / n[a["group"]]
                                                for a in flips), 2)}
        differ |= {d["id"] for d in ag["diffs"]}
    bounds = [p["points_bound"] for p in per.values() if p and "points_bound" in p]
    return {"samples": per, "keys_that_differ": sorted(differ),
            "sigma_extract_bound": round(math.sqrt(statistics.mean(b * b for b in bounds) / 2), 2)
            if bounds else None}


def cmd_noise(args) -> None:
    """Spread between student samples, between judge passes and (with --extract-passes 2) between
    extraction passes of one iteration; noise estimates and the iteration threshold go to
    noise.json, noise.md and state.json."""
    state = load_state(args.run)
    k = args.iter
    scored = scored_samples(args.run, state, k)
    left_out = [label for label, _s, _c in iteration_samples(args.run, k)
                if label not in {x[0] for x in scored}]
    samples = [(label, sc, c) for label, _s, c, sc in scored]
    if len(samples) < 2:
        die(f"iteration {k} has {len(samples)} valid scored sample(s); the noise baseline needs at least 2 "
            f"(student --samples 3, then compare --judges 2)")
    counts = sorted({score_judges(sc) for _l, sc, _c in samples})
    if len(counts) > 1:
        die(f"iteration {k}'s samples were scored with different numbers of judge passes ({counts}); "
            f"re-run `compare --iter {k} --judges N`")
    J = counts[0]
    if J < 2:
        die(f"iteration {k} was scored with one judge pass; re-run `compare --iter {k} --judges 2`")
    if len(samples) < 3:
        log(f"warning: {len(samples)} valid samples; the spread between students is barely estimated")
    j_iter = args.judges or CFG.get("judges", 1)
    extract = None
    if args.extract_passes >= 2:
        verify_frozen(args.run, state)
        check_inputs_unchanged(args.run, args.allow_drift)
        extract = extraction_noise(args.run, state, scored)

    means = [sc["total"] for _l, sc, _c in samples]
    within = statistics.mean(statistics.variance([j["total"] for j in sc["judges"]]) for _l, sc, _c in samples)
    sigma_judge = math.sqrt(within)
    # Not reduced by within / J: with a handful of samples that difference is often clamped to 0,
    # which would leave only judge noise in the threshold. Uncorrected, the estimate errs high.
    var_student = statistics.variance(means)
    one_sample = mean_score_variance(var_student, within, 1, j_iter)
    sigma_iter = math.sqrt(one_sample)
    threshold = significance_threshold(one_sample, one_sample)

    dims = {}
    for d in DIMENSIONS:
        per_sample = [[dim_points(j["dimensions"])[d] for j in sc["judges"]] for _l, sc, _c in samples]
        dims[d] = {"between_samples_sd": round(sd([statistics.mean(x) for x in per_sample]), 2),
                   "within_sample_sd": round(math.sqrt(statistics.mean(statistics.variance(x) for x in per_sample)), 2)}
    agree = {label: effective_agreement(c) for label, _sc, c in samples}
    ids = set().union(*(set(a) for a in agree.values()))
    sample_flips = sorted(i for i in ids if len({a.get(i) for a in agree.values() if i in a}) > 1)
    result = {
        "iter": k, "samples": len(samples), "judges": J, "judges_per_iteration": j_iter,
        "sample_totals": {label: sc["total"] for label, sc, _c in samples},
        "judge_totals": {label: [j["total"] for j in sc["judges"]] for label, sc, _c in samples},
        "between_samples": {"mean": round(statistics.mean(means), 2), "sd": round(sd(means), 2),
                            "min": min(means), "max": max(means)},
        "within_sample": {"pooled_sd": round(sigma_judge, 2),
                          "max_diff": max(max(t) - min(t) for t in
                                          ([j["total"] for j in sc["judges"]] for _l, sc, _c in samples))},
        "dimensions_points": dims,
        "soft_parts": {label: [j.get("soft_parts", {}) for j in sc["judges"]] for label, sc, _c in samples},
        "flips_between_samples": sample_flips,
        "flips_between_judges": {label: judge_flips(c) for label, _sc, c in samples},
        "sigma_judge": round(sigma_judge, 2), "sigma_student": round(math.sqrt(var_student), 2),
        "var_judge": round(within, 4), "var_student": round(var_student, 4),
        "sigma_iteration": round(sigma_iter, 2), "threshold": threshold, "left_out": left_out,
        "extraction": extract, "measured_at": timestamp(),
    }
    write_json(run_dir(args.run) / "noise.json", result)
    out = ["# 噪声基线", "",
           f"第 {k} 轮，{len(samples)} 个 student 样本 × 每样本 {J} 次独立评审（裁定 + 软性分项）。"
           + (f"未计入（student 运行无效或未打分）：{', '.join(left_out)}。" if left_out else ""), "",
           "| 样本 | 均值 | 各评审总分 |", "|---|---|---|"]
    out += [f"| {label} | {sc['total']} | {', '.join(str(j['total']) for j in sc['judges'])} |"
            for label, sc, _c in samples]
    out += ["", f"- 样本间：均值 {result['between_samples']['mean']}，标准差 {result['between_samples']['sd']}"
            f"（{min(means)} – {max(means)}）",
            f"- 样本内（评审间）：合并标准差 {result['within_sample']['pooled_sd']}，最大差 "
            f"{result['within_sample']['max_diff']}",
            f"- σ_judge = sqrt(样本内方差均值) = {result['sigma_judge']}",
            f"- σ_student = sqrt(var(样本均值)) = {result['sigma_student']}：不扣除其中的评审部分 "
            f"σ²_judge / {J}，因为样本很少时扣除后常被截成 0，阈值随之偏小；不扣除则偏保守",
            "- 一轮分数是 n 个有效样本、每个 J 次评审的均值，方差 = σ²_student / n + σ²_judge / (n·J)",
            f"- **两轮分数之差超过 2 × sqrt(方差_a + 方差_b) 才算显著**；两轮都是 1 个样本、{j_iter} 次评审时，"
            f"σ = {result['sigma_iteration']}，阈值 = 2 × √2 × σ = **{threshold}**。消融实验用 Welch t 检验。", "",
            "## 各维度（分值，满分为权重）", "", "| 维度 | 样本间标准差 | 样本内标准差 |", "|---|---|---|"]
    out += [f"| {d} | {v['between_samples_sd']} | {v['within_sample_sd']} |" for d, v in dims.items()]
    out += ["", "## 结果翻转的决策项", "",
            f"- 样本之间（是否计为一致）：{', '.join(f'`{i}`' for i in sample_flips) or '无'}"]
    if extract:
        sensitive = sorted(set(sample_flips) & set(extract["keys_that_differ"]))
        out.append(f"  - 其中提取器两次提取也不一致、不能只归因于 student 的："
                   f"{', '.join(f'`{i}`' for i in sensitive) or '无'}")
    out += [f"- 样本 {label} 的评审之间（裁定不同）：{', '.join(f'`{i}`' for i in f) or '无'}"
            for label, f in result["flips_between_judges"].items()]
    if extract:
        out += ["", "## 提取器噪声（同一 spec 的两次独立提取）", "",
                "每个样本只提取一次，所有评审共用这一份提取结果，所以提取器的噪声算在 σ_student 里。"
                "这里对每个样本再提取一次：", "",
                "| 样本 | 两次一致率 | 至少一次有值的键一致率 | 不一致的键 | 一致性翻转的决策项 | 最多影响分数 |",
                "|---|---|---|---|---|---|"]
        for label, p in extract["samples"].items():
            out.append(f"| {label} | 提取失败 | - | - | - | - |" if p is None else
                       f"| {label} | 未比较：缺少第一次提取或模块表 | - | - | - | - |" if p.get("skipped") else
                       f"| {label} | {p['agreement']:.1%} | {p['stated_agreement']:.1%} | "
                       f"{', '.join(f'`{i}`' for i in p['keys_that_differ']) or '无'} | "
                       f"{', '.join(f'`{i}`' for i in p['agreement_flips']) or '无'} | {p['points_bound']} |")
        out += ["", f"σ_extract ≤ {extract['sigma_extract_bound']}（上界：一致性翻转的决策项都按改变分数计，"
                    f"争议裁定可能抵消其中一部分）。"]
    (run_dir(args.run) / "noise.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    with state_update(args.run) as state:
        state["noise"] = {**{key: result[key] for key in ("iter", "samples", "judges", "judges_per_iteration",
                                                          "sigma_judge", "sigma_student", "var_judge", "var_student",
                                                          "sigma_iteration", "threshold", "measured_at")},
                          "sigma_extract_bound": extract["sigma_extract_bound"] if extract else None}
    log(f"noise: sigma_judge {result['sigma_judge']}, sigma_student {result['sigma_student']}, "
        f"sigma per iteration {result['sigma_iteration']}; threshold {threshold} for two 1-sample iterations"
        + (f", sigma_extract <= {extract['sigma_extract_bound']}" if extract else "")
        + f" ({run_dir(args.run) / 'noise.md'})")
    for j in sorted(iteration_scores(state)):
        if j > 0:
            mark_iteration(args.run, state, j)
