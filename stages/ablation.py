"""ablate: the selected playbook against no playbook, on fresh students."""

from __future__ import annotations

import re
import statistics

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from lib import decisions as dec
from lib.common import (die, iter_dir, load_state, log, read_json, remove_tree, run_dir, state_update, write_json,
                        write_text_atomic)
from lib.stats import welch

from .core import CFG, DIMENSIONS, dim_points, reference_decisions, score_judges, sd, student_valid, verify_frozen
from .provenance import check_inputs_unchanged, json_digest, reuse_mode, score_provenance
from .student import playbook_prompt, prompt_differs, run_student, student_attempts
from .marks import best_playbook_iter, iteration_scores, majority_gaps, scored_samples
from .scoring import score_or_reuse
from .synthesis import playbook_report


ARMS = ("none", "full", "process_only")
ARM_PAIRS = (("process_only", "none"), ("full", "process_only"), ("full", "none"))
PRIMARY_PAIR = ("full", "none")


# With two samples an arm's standard deviation is barely estimated.
MIN_ARM_SAMPLES = 3


def arm_summary(scored: list[tuple[Path, Path, dict, int | None]]) -> dict:
    """One arm from (student dir, compare dir, score, attempts) of its scored samples."""
    scores = [sc for _s, _c, sc, _a in scored]
    totals = [s["total"] for s in scores]
    points = [dim_points({d: s["dimensions"][d]["value"] for d in DIMENSIONS}) for s in scores]
    groups = [*dec.GROUPS, *dec.ALL_KINDS]
    return {"n": len(scores), "mean": round(statistics.mean(totals), 2), "sd": round(sd(totals), 2),
            "min": min(totals), "max": max(totals), "totals": totals,
            "dimensions": {d: round(statistics.mean(p[d] for p in points), 2) for d in DIMENSIONS},
            "agreement": {g: round(statistics.mean(s["agreement"][g]["value"] for s in scores), 4)
                          for g in groups if all(g in s.get("agreement", {}) for s in scores)},
            "gaps": sorted(majority_gaps(scores)),
            "attempts": [a for _s, _c, _sc, a in scored],
            "student_cli": sorted({read_json(s / "trajectory.run.json", {}).get("agent_cli") or "unknown"
                                   for s, _c, _sc, _a in scored}),
            "judge_inputs": sorted({json_digest(sc["provenance"]["inputs"])[:12] if sc.get("provenance")
                                    else "unstamped" for sc in scores}),
            "compare_dirs": [str(c) for _s, c, _sc, _a in scored]}


def cmd_ablate(args) -> None:
    """Arms judged the same way: none (the iteration-0 samples, no new runs) against full (fresh
    students with the selected playbook); optionally process_only (the same playbook with every line
    a strict leak pass flags removed)."""
    state = load_state(args.run)
    verify_frozen(args.run, state)
    check_inputs_unchanged(args.run, args.allow_drift)
    rd, judges, samples = run_dir(args.run), args.judges or CFG.get("judges", 1), max(MIN_ARM_SAMPLES, args.samples)
    new_arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    if not new_arms or any(a not in ARMS[1:] for a in new_arms):
        die(f"--arms takes a comma-separated subset of {', '.join(ARMS[1:])}")
    if args.playbook == "top":
        best = best_playbook_iter(state)
        if best is None:
            die("no iteration with a playbook has a score yet; run `loop.py iterate` first")
        src = best - 1
    else:
        m = re.fullmatch(r"iter-(\d+)", args.playbook)
        if not m:
            die("--playbook is `top` or `iter-NN` (the iteration whose playbook/ holds it)")
        src = int(m.group(1))
    pb = iter_dir(args.run, src) / "playbook" / "playbook.md"
    if not pb.exists():
        die(f"no playbook at {pb}")
    name = f"iter-{src:02d}"
    none = [(s, c, sc, student_attempts(state, 0, label, s)) for label, s, c, sc in scored_samples(args.run, state, 0)]
    if len(none) < MIN_ARM_SAMPLES:
        die(f"the none arm reuses the valid scored iteration-0 samples and has {len(none)}; at least "
            f"{MIN_ARM_SAMPLES} are needed (student --iter 0 --samples 3, then compare)")
    none_judges = sorted({score_judges(sc) for _s, _c, sc, _a in none})
    if none_judges != [judges]:
        die(f"the none arm was judged with {none_judges} judge pass(es) per sample and the new arms would get "
            f"{judges}; pass --judges {none_judges[0]} or re-run `compare --iter 0 --judges {judges}`")
    modes = {str(c): reuse_mode(sc, score_provenance(args.run, state, s, judges)) for s, c, sc, _a in none}
    differ = [c for c, m in modes.items() if m in ("none", "aggregate")]
    if differ:
        msg = (f"the none arm was scored under other inputs, scoring code or student specs than the new arms "
               f"would be: {', '.join(differ)}")
        if not args.allow_drift:
            die(f"{msg}; re-run `compare --iter 0`, or pass --allow-drift to compare the arms anyway")
        log(f"warning: {msg} (--allow-drift)")
    if "legacy" in modes.values():
        log(f"warning: the none arm's scores predate provenance stamps; whether they were judged under the "
            f"same inputs cannot be checked ({list(modes.values()).count('legacy')} sample(s))")

    abl = rd / "ablation"
    previous = state.get("ablation", {}).get("playbook")
    if previous and previous != name:
        if not args.force:
            die(f"runs/{args.run}/ablation/ tests playbook {previous}; pass --force to replace it with {name}")
        remove_tree(abl)
    full = abl / "playbook.full.md"
    if not full.exists():
        write_text_atomic(full, pb.read_text(encoding="utf-8"))
    process_only = abl / "playbook.process_only.md"
    if "process_only" in new_arms and not process_only.exists():
        report = playbook_report(args.run, state, full, reference_decisions(args.run, state), abl / "strict-leak",
                                 "ablation-strict-leak", strict=True)
        write_json(abl / "process_only_strip.json", report)
        write_text_atomic(process_only, dec.strip_lines(full.read_text(encoding="utf-8"),
                                                        [e["line"] for e in report["leak_lines"]]))
        log(f"process-only playbook: {len(report['leak_lines'])} of {report.get('lines')} lines removed "
            f"({process_only})")
    with state_update(args.run) as state:
        state["ablation"] = {"playbook": name, "arms": ["none", *new_arms], "samples": samples, "judges": judges,
                             "based_on_score": iteration_scores(state).get(src + 1)}
    playbooks = {"full": full, "process_only": process_only}
    texts = {arm: playbook_prompt(state, playbooks[arm].read_text(encoding="utf-8")) for arm in new_arms}
    jobs = [(arm, s) for arm in texts for s in range(1, samples + 1)]
    stale = [str(abl / arm / f"student-s{s}") for arm, s in jobs
             if student_valid(abl / arm / f"student-s{s}") and prompt_differs(abl / arm / f"student-s{s}", texts[arm])]
    if stale:
        die(f"{', '.join(stale)} were run with another prompt than their arm's; delete them to run them again")

    def student_job(arm: str, s: int):
        sdir = abl / arm / f"student-s{s}"
        if not student_valid(sdir):
            run_student(args.run, state, sdir, f"ablation-{arm}-student-s{s}", texts[arm], f"ablation {arm} s{s}",
                        f"-s{s}")

    def compare_job(arm: str, s: int):
        sdir, cdir = abl / arm / f"student-s{s}", abl / arm / f"compare-s{s}"
        if not student_valid(sdir):
            log(f"ablation {arm} s{s}: no valid student run; left out")
            return None
        sc = score_or_reuse(args.run, state, f"ablation-{arm}-compare-s{s}", sdir, cdir, judges, legacy_ok=True)
        return (sdir, cdir, sc, read_json(sdir / "provenance.json", {}).get("attempts")) if sc else None

    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        list(pool.map(lambda j: student_job(*j), jobs))
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        scored = dict(zip(jobs, pool.map(lambda j: compare_job(*j), jobs)))

    arms = {"none": arm_summary(none)}
    for arm in texts:
        got = [scored[(arm, s)] for s in range(1, samples + 1) if scored.get((arm, s))]
        if len(got) < MIN_ARM_SAMPLES:
            die(f"ablation arm {arm} has {len(got)} scored sample(s); at least {MIN_ARM_SAMPLES} are needed "
                f"(re-run `ablate` to retry the invalid or failed ones, or raise --samples)")
        arms[arm] = arm_summary(got)
    pairs = []
    for a, b in ARM_PAIRS:
        if a not in arms or b not in arms:
            continue
        A, B = arms[a], arms[b]
        pairs.append({"a": a, "b": b, "primary": (a, b) == PRIMARY_PAIR, **welch(A["totals"], B["totals"]),
                      "dimensions": {d: round(A["dimensions"][d] - B["dimensions"][d], 2) for d in DIMENSIONS},
                      "agreement": {g: round(A["agreement"][g] - B["agreement"][g], 4)
                                    for g in A["agreement"] if g in B["agreement"]},
                      "gaps_closed": sorted(set(B["gaps"]) - set(A["gaps"])),
                      "gaps_opened": sorted(set(A["gaps"]) - set(B["gaps"]))})
    result = {"playbook": name, "playbook_iteration_score": iteration_scores(state).get(src + 1),
              "samples": samples, "judges": judges, "arms": arms, "pairs": pairs,
              "noise": state.get("noise"),
              "process_only_lines_removed": len(read_json(abl / "process_only_strip.json", {}).get("leak_lines", []))
              if "process_only" in arms else None}
    write_json(abl / "ablation.json", result)
    (abl / "report.md").write_text(render_ablation(result), encoding="utf-8")
    for p in pairs:
        log(f"ablation {p['a']} - {p['b']}{' (primary)' if p['primary'] else ''}: {p['diff']:+.1f}, Welch t "
            f"{p['t']} (df {p['df']}), critical difference {p['critical_diff']}, p {p['p']}: "
            f"{'significant' if p['significant'] else 'not significant'}")
    log(f"ablation report: {abl / 'report.md'}")


def render_ablation(r: dict) -> str:
    label = {"none": "无 playbook", "full": "完整 playbook", "process_only": "仅过程（剔除答案行）"}
    out = ["# 消融实验", "",
           f"被测 playbook：`{r['playbook']}`（它所在轮的原始分数 {r['playbook_iteration_score']}；该分数因择优而偏高，"
           f"这里用新样本重测）。无 playbook 组复用第 0 轮的基线样本。每组每个样本由 {r['judges']} 次独立评审打分，"
           f"样本分为评审均值。"
           + (f"仅过程组剔除了严格泄漏检查标出的 {r['process_only_lines_removed']} 行"
              f"（任何决策值，包括 AGENTS.md 已定的；任何 HMOS 符号；HMOS 代码行为结论）。"
              if r.get("process_only_lines_removed") is not None else ""), "",
           "| 组 | n | 均值 | 标准差 | 范围 | 每个样本的 student 尝试次数 |", "|---|---|---|---|---|---|"]
    def cell(v) -> str:
        return "-" if v is None else str(v)

    for arm, a in r["arms"].items():
        tries = ", ".join("?" if t is None else str(t) for t in a["attempts"])
        out.append(f"| {label[arm]} | {a['n']} | {a['mean']} | {a['sd']} | {a['min']} – {a['max']} | {tries} |")
    out += ["", "尝试次数大于 1 表示之前的尝试无效（运行失败、交付物不全或泄漏）被重跑；只统计最后一次有效的。"
            "某组需要重跑得更多，说明它的均值没有反映失败的代价。"]
    clis = {arm: a["student_cli"] for arm, a in r["arms"].items()}
    inputs = {arm: a["judge_inputs"] for arm, a in r["arms"].items()}
    if len({tuple(v) for v in clis.values()}) > 1 or any(len(v) > 1 for v in clis.values()):
        out += ["", "**条件不一致**：各组 student 使用的 agent CLI 版本不同（"
                + "；".join(f"{label[arm]} {', '.join(v)}" for arm, v in clis.items()) + "），差值里混有 CLI 的影响。"]
    if len({tuple(v) for v in inputs.values()}) > 1 or any(len(v) > 1 for v in inputs.values()):
        out += ["", "**条件不一致**：各组打分时的输入（提示词、配置、模型、CLI）指纹不同或无记录（"
                + "；".join(f"{label[arm]} {', '.join(v)}" for arm, v in inputs.items()) + "）。"]
    out += ["", "## 两两比较", "",
            "Welch t 检验，双侧 α = 0.05，自由度按 Welch–Satterthwaite 计算，用各组自己的样本间离散度；"
            "每组只有几个样本时临界值明显大于 2（自由度 4 时约 2.8）。“完整 − 无”是唯一的主比较；"
            "其余比较是探索性的，未做多重比较校正。", "",
            "| 比较 | 含义 | 差值 | SE | 自由度 | 临界差值 | p | 结论 |", "|---|---|---|---|---|---|---|---|"]
    meaning = {("process_only", "none"): "教过程的价值", ("full", "process_only"): "残留答案内容的价值（应接近 0）",
               ("full", "none"): "playbook 的总效果"}
    for p in r["pairs"]:
        role = "主比较" if p["primary"] else "探索性"
        out.append(f"| {label[p['a']]} − {label[p['b']]}（{role}） | {meaning[(p['a'], p['b'])]} | {p['diff']:+.1f} | "
                   f"{p['se']} | {cell(p['df'])} | {cell(p['critical_diff'])} | {cell(p['p'])} | "
                   f"{'显著' if p['significant'] else '不显著'} |")
    out += ["", "## 各维度（分值差）", "", "| 维度 | " + " | ".join(f"{label[p['a']]} − {label[p['b']]}"
                                                         for p in r["pairs"]) + " |",
            "|---|" + "---|" * len(r["pairs"])]
    for d in DIMENSIONS:
        out.append(f"| {d} | " + " | ".join(f"{p['dimensions'][d]:+.2f}" for p in r["pairs"]) + " |")
    out += ["", "## 决策一致率（分组与类别）", "",
            "| 分组 / 类别 | " + " | ".join(label[a] for a in r["arms"]) + " |", "|---|" + "---|" * len(r["arms"])]
    for g in r["arms"]["none"]["agreement"]:
        out.append(f"| {g} | " + " | ".join(f"{a['agreement'].get(g, '-')}" for a in r["arms"].values()) + " |")
    out += ["", "## 差距 id 变化（按多数样本计）", ""]
    for p in r["pairs"]:
        out.append(f"- {label[p['a']]} 相对 {label[p['b']]}：关闭 "
                   f"{', '.join(f'`{i}`' for i in p['gaps_closed']) or '无'}；新出现 "
                   f"{', '.join(f'`{i}`' for i in p['gaps_opened']) or '无'}")
    noise = r.get("noise") or {}
    if noise:
        base_sd = r["arms"]["none"]["sd"]
        wide = [label[a] for a, v in r["arms"].items() if a != "none" and base_sd and v["sd"] > 2 * base_sd]
        out += ["", "## 与噪声基线的对照", "",
                f"噪声基线 σ_student {noise.get('sigma_student')}，两轮都只有 1 个样本时的轮间阈值 {noise.get('threshold')}。"
                + (f"{'、'.join(wide)} 的样本间离散度超过无 playbook 组的两倍，建议按带 playbook 的离散度更新阈值。"
                   if wide else "各组离散度与无 playbook 组相当，阈值无需更新。")]
    return "\n".join(out) + "\n"
