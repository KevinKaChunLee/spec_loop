"""compare and rescore: extraction, disputes, soft judge and the total of each student sample."""

from __future__ import annotations

import json
import re
import shutil
import statistics

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from lib import decisions as dec
from lib import spec_metrics, workspace
from lib.common import ROOT, die, iter_dir, load_state, log, prompt, read_json, run_dir, state_update, write_json

from .core import (CFG, DIMENSIONS, SCORING, base_dir, hmos_index, iteration_samples, oracle_dir, oracle_spec,
                   read_csv, reference_decisions, reuse_json, sample_label, score_judges, student_valid,
                   task_text, verify_frozen, write_csv)
from .provenance import check_inputs_unchanged, reuse_mode, score_provenance
from .agents import run_checked_agent
from .extraction import extract_spec
from .student import student_attempts
from .marks import mark_iteration


SEVERITIES = {"high", "medium", "low"}
TAGS = {"student_wrong", "student_defensible", "reference_questionable"}
SOFT_PARTS = {"requirements_correctness": "baseline_coverage", "scenario_quality": "testability_grounding",
              "design_quality": "code_level_design", "readability": "readability_rules"}


def run_disputes(run_id: str, state: dict, stage: str, out_dir: Path, disputes: list[dict],
                 stu_spec: Path, title: str) -> dict | None:
    """One ruling per disagreement. A run that still leaves rulings out or invalid after its fix
    retries fails, like a soft judge that does not deliver: defaulting them would charge the
    student for the judge."""
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out_dir / "_staging"
    tmp.mkdir(exist_ok=True)
    write_json(tmp / "disputes.json", disputes)
    (tmp / "task.md").write_text(task_text(state), encoding="utf-8")
    ws = workspace.build(CFG, run_id, stage, {"disputes.json": tmp / "disputes.json", "task.md": tmp / "task.md",
                                              "reference": oracle_spec(run_id), "student": stu_spec})
    ids = [d["id"] for d in disputes]
    rulings, errors = run_checked_agent(state, "judge", run_id, ws, prompt("disputes.md", change_name=CFG["change_name"]),
                                        out_dir, "rulings.json", lambda raw: dec.validate_rulings(raw, ids),
                                        CFG.get("judge_fix_retries", 0), title, ("rulings.json",))
    shutil.rmtree(tmp, ignore_errors=True)
    if errors:
        log(f"{title} FAILED: " + "; ".join(errors[:5]))
        return None
    write_json(out_dir / "rulings.checked.json", {"rulings": rulings})
    return rulings


def check_soft(data) -> tuple[dict | None, list[str]]:
    errors = []
    if not isinstance(data, dict):
        return None, ["top level must be an object"]
    parts = data.get("parts")
    if not isinstance(parts, dict):
        errors.append("missing object 'parts'")
        parts = {}
    for key in SOFT_PARTS:
        entry = parts.get(key)
        if not isinstance(entry, dict):
            errors.append(f"parts.{key} is missing")
            continue
        s = entry.get("score")
        if not isinstance(s, int) or isinstance(s, bool) or not 0 <= s <= 5:
            errors.append(f"parts.{key}.score must be an integer 0-5 (got {s!r})")
    gaps = data.get("gaps")
    if not isinstance(gaps, list):
        errors.append("missing list 'gaps'")
        gaps = []
    dims = sorted(set(SOFT_PARTS.values()))
    for i, g in enumerate(gaps):
        if not isinstance(g, dict):
            errors.append(f"gaps[{i}] must be an object")
            continue
        for field in ("id", "summary"):
            if not isinstance(g.get(field), str) or not g.get(field):
                errors.append(f"gaps[{i}].{field} is missing")
        if g.get("dimension") not in dims:
            errors.append(f"gaps[{i}].dimension must be one of {dims}")
        if g.get("severity") not in SEVERITIES:
            errors.append(f"gaps[{i}].severity must be one of {sorted(SEVERITIES)}")
        if g.get("tag") not in TAGS:
            errors.append(f"gaps[{i}].tag must be one of {sorted(TAGS)}")
    return data, errors[:30]


def run_soft_judge(run_id: str, state: dict, stage: str, out_dir: Path, stu_dir: Path,
                   metrics_md: Path, code_checks_md: Path, title: str) -> dict | None:
    """The judge sees the same inputs in every iteration, the noise baseline and the ablation."""
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out_dir / "_staging"
    tmp.mkdir(exist_ok=True)
    (tmp / "task.md").write_text(task_text(state), encoding="utf-8")
    inputs = {"task.md": tmp / "task.md", "rubric.md": ROOT / "rubric.md",
              "reference": oracle_spec(run_id), "student": stu_dir / "spec",
              "metrics.md": metrics_md, "code_checks.md": code_checks_md}
    ws = workspace.build(CFG, run_id, stage, inputs)
    data, errors = run_checked_agent(state, "judge", run_id, ws, prompt("compare.md", change_name=CFG["change_name"]),
                                     out_dir, "soft_score.json", check_soft, CFG.get("judge_fix_retries", 0),
                                     title, ("soft_score.json", "soft_report.md"),
                                     also=" (and `_outputs/soft_report.md` if the scores change)")
    shutil.rmtree(tmp, ignore_errors=True)
    if errors:
        log(f"{title} FAILED: " + "; ".join(errors[:5]))
        return None
    return data


def render_code_checks(coverage: dict, behaviour: dict, grounding: float, tasks: dict, build: dict,
                       rules: dict) -> str:
    out = ["# Script checks of the student spec", "",
           "Computed by the script and scored without you. Do not score these again.", "",
           f"- HMOS module directories covered by a baseline capability: {coverage['value']:.2f}"
           f" (not covered: {', '.join(coverage['missing']) or 'none'})",
           f"- Behaviour coverage: the student's baseline specs cite {behaviour['recall']:.0%} of the "
           f"{behaviour['reference_names']} HMOS names the reference's baseline cites ({behaviour['student_names']} "
           f"names cited in total, padding factor {behaviour['padding_factor']}). Whether the requirements "
           f"around those names describe the behaviour correctly is yours to judge.",
           f"- Reference grounding (backticked names found in the HMOS tree): {grounding:.3f}",
           f"- tasks.md rules (gate per group, gtest per group, gni sync on deletions): {tasks['value']:.2f} "
           f"{json.dumps(tasks.get('parts', {}))}",
           f"- callmanager.gni / bundle.json coverage: {build['value']:.2f}",
           f"- Readability checklist: {rules['value']:.2f}"]
    out += [f"  - {k}: {c['value']} {c['detail']}" for k, c in rules["checks"].items()]
    return "\n".join(out) + "\n"


def shared_idents(run_id: str, state: dict) -> set[str]:
    base = base_dir(run_id)
    texts = [(base / rel).read_text(encoding="utf-8", errors="replace")
             for rel in ("AGENTS.md", "openspec/config.yaml") if (base / rel).exists()]
    return dec.allowed_symbols([*texts, task_text(state)])[0]


def score_sample(run_id: str, state: dict, stage: str, stu_dir: Path, out_dir: Path,
                 ref_table: dict, provenance: dict, stu_table: dict | None = None, reuse: bool = False,
                 judges: int = 1) -> dict | None:
    """Score one student spec: code checks, then (in parallel) extraction -> table diff -> disputes,
    and the soft judge; aggregate in code. Writes score.json (stamped with `provenance`),
    report.md and decisions_compare.json.
    With `judges` > 1, each judge pass (disputes + soft judge) is independent and kept in
    judge-M/; the sample's total is the mean of the passes' totals, gaps use majority rulings.
    With `reuse`, model outputs already in `out_dir` (extraction, rulings covering every dispute,
    soft score) are taken as they are, so a change to the scoring code needs no new agent runs."""
    if not (stu_dir / "spec").exists():
        die(f"no student spec at {stu_dir / 'spec'}")
    index, vocab = hmos_index(run_id), dec.load_vocab()
    ref_m = spec_metrics.collect(oracle_spec(run_id), base_dir(run_id), CFG, index)
    stu_m = read_json(stu_dir / "metrics.json") or \
        spec_metrics.collect(stu_dir / "spec", base_dir(run_id), CFG, index)
    d = spec_metrics.diff(ref_m, stu_m)
    out_dir.mkdir(parents=True, exist_ok=True)
    stu_guards = read_json(stu_dir / "guards.json", {})
    md = spec_metrics.render_md(ref_m, stu_m, d, read_json(oracle_dir(run_id) / "guards.json", {}), stu_guards)
    (out_dir / "metrics.md").write_text(md, encoding="utf-8")
    write_json(out_dir / "metrics_diff.json", d)

    ref_mod = dec.module_table(oracle_spec(run_id), index, CFG)
    stu_mod = dec.module_table(stu_dir / "spec", index, CFG)
    modules = dec.all_modules(index)
    missing = sorted(set(modules) - set(stu_mod["covered"]))
    coverage = {"value": round(1 - len(missing) / len(modules), 4), "missing": missing}
    grounding = stu_m.get("reference_grounding") or 0.0
    tasks = dec.task_rules(stu_dir / "spec", CFG)
    build = dec.build_coverage(oracle_spec(run_id), stu_dir / "spec", base_dir(run_id), CFG)
    rules = dec.rule_checklist(stu_dir / "spec", CFG, stu_guards.get("validate", {}).get("ok"), stu_mod)
    shared = shared_idents(run_id, state)
    behaviour = dec.behaviour_coverage(dec.cited_names(oracle_spec(run_id), CFG, index, shared),
                                       dec.cited_names(stu_dir / "spec", CFG, index, shared),
                                       SCORING["coverage_padding_ratio"])
    (out_dir / "code_checks.md").write_text(
        render_code_checks(coverage, behaviour, grounding, tasks, build, rules), encoding="utf-8")
    if reuse and stu_table is None:
        stu_table = reuse_json(out_dir / "decisions" / "decisions.json", lambda d: "features" in d)
    jdirs = [out_dir] if judges <= 1 else [out_dir / f"judge-{m}" for m in range(1, judges + 1)]
    jtag = (lambda m: "") if judges <= 1 else (lambda m: f"-j{m}")

    def soft_pass(m: int, jdir: Path):
        old = reuse_json(jdir / "soft" / "soft_score.json", lambda d: not check_soft(d)[1]) if reuse else None
        return old or run_soft_judge(run_id, state, f"{stage}-soft{jtag(m)}", jdir / "soft", stu_dir,
                                     out_dir / "metrics.md", out_dir / "code_checks.md",
                                     f"soft judge {stage}{jtag(m)}")

    def dispute_pass(m: int, jdir: Path, disputes: list[dict]):
        if not disputes:
            return {}
        ids = {d["id"] for d in disputes}
        old = reuse_json(jdir / "disputes" / "rulings.checked.json",
                         lambda d: ids <= set(d.get("rulings", {}))) if reuse else None
        if old is not None:
            return {i: old["rulings"][i] for i in ids}
        return run_disputes(run_id, state, f"{stage}-disputes{jtag(m)}", jdir / "disputes", disputes,
                            stu_dir / "spec", f"disputes {stage}{jtag(m)}")

    with ThreadPoolExecutor(max_workers=2 * len(jdirs) + 1) as pool:
        f_table = pool.submit(lambda: stu_table if stu_table is not None else extract_spec(
            run_id, state, stu_dir / "spec", out_dir / "decisions", f"{stage}-extract",
            f"extract {stu_dir.relative_to(run_dir(run_id))}"))
        f_soft = [pool.submit(soft_pass, m, jd) for m, jd in enumerate(jdirs, 1)]
        table = f_table.result()
        items = disputes = None
        f_rul = []
        if table is not None:
            items = dec.compare(ref_table, table, ref_mod, stu_mod, vocab, index)
            disputes = dec.dispute_inputs(items, ref_table, table, ref_mod, stu_mod, vocab)
            log(f"{stage}: {len(items) - len(disputes)} of {len(items)} decisions agree; "
                f"{len(disputes)} to dispute")
            f_rul = [pool.submit(dispute_pass, m, jd, disputes) for m, jd in enumerate(jdirs, 1)]
        softs = [f.result() for f in f_soft]
        rulings_list = [f.result() for f in f_rul]
    if table is None or any(s is None for s in softs) or any(r is None for r in rulings_list):
        return None

    checks = {"module_coverage": coverage,
              "behaviour_coverage": {**behaviour, "missing": behaviour["missing"][:200]},
              "grounding_rate": grounding, "task_rules": tasks, "build_coverage": build, "rule_checklist": rules}
    code_parts = {"module_coverage": coverage["value"], "behaviour_coverage": behaviour["value"],
                  "grounding_rate": grounding, "task_rules": tasks["value"], "build_coverage": build["value"],
                  "rule_checklist": rules["value"]}
    code_gaps = dec.check_gaps(missing, behaviour, rules, tasks)

    def assemble(rulings: dict, soft_parts: dict[str, float], rationales: dict[str, str],
                 soft_gaps: list[dict]) -> dict:
        agree = dec.agreement(items, rulings)
        parts = {part: agree[group]["value"] for group, part in dec.GROUP_PART.items()}
        parts.update(code_parts)
        parts.update(soft_parts)
        dims, total = dec.aggregate(SCORING, parts)
        for p, dim in SOFT_PARTS.items():
            dims[dim]["rationale"] = rationales.get(p, "")
        return {"scoring": "decisions-v2", "total": total, "dimensions": dims, "weights": SCORING["weights"],
                "agreement": agree, "code_share": dec.code_share(SCORING, parts, agree),
                "disputes": len(disputes), "gaps": dec.decision_gaps(items, rulings, vocab) + code_gaps + soft_gaps,
                "code_checks": checks}

    def soft_report(jdir: Path) -> str:
        p = jdir / "soft" / "soft_report.md"
        return p.read_text(encoding="utf-8") if p.exists() else ""

    per_judge = [assemble(r, {p: s["parts"][p]["score"] / 5 for p in SOFT_PARTS},
                          {p: s["parts"][p].get("rationale", "") for p in SOFT_PARTS},
                          [{**g, "source": "judge"} for g in s.get("gaps", [])])
                 for r, s in zip(rulings_list, softs)]
    if judges <= 1:
        score, rulings, report_soft = per_judge[0], rulings_list[0], soft_report(out_dir)
    else:
        for m, (jd, sc) in enumerate(zip(jdirs, per_judge), 1):
            write_json(jd / "score.json", sc)
            (jd / "report.md").write_text(dec.render_report(sc, items, rulings_list[m - 1], coverage, behaviour,
                                                            rules, tasks, build, soft_report(jd), vocab),
                                          encoding="utf-8")
        rulings = dec.majority_rulings(rulings_list)
        soft_gaps, seen = [], set()
        for m, s in enumerate(softs, 1):
            for g in s.get("gaps", []):
                if g.get("id") not in seen:
                    seen.add(g.get("id"))
                    soft_gaps.append({**g, "source": "judge", "judge": m})
        score = assemble(rulings, {p: statistics.mean(s["parts"][p]["score"] for s in softs) / 5 for p in SOFT_PARTS},
                         {p: " | ".join(f"J{m}: {s['parts'][p].get('rationale', '')}" for m, s in enumerate(softs, 1))
                          for p in SOFT_PARTS}, soft_gaps)
        totals = [sc["total"] for sc in per_judge]
        score["total"] = round(statistics.mean(totals), 1)
        for dim in DIMENSIONS:
            v = statistics.mean(sc["dimensions"][dim]["value"] for sc in per_judge)
            score["dimensions"][dim].update(value=round(v, 4), score=round(v * 5, 2))
        score["judges"] = [{"judge": m, "total": sc["total"],
                            "dimensions": {d: sc["dimensions"][d]["value"] for d in DIMENSIONS},
                            "soft_parts": {p: s["parts"][p]["score"] for p in SOFT_PARTS}}
                           for m, (sc, s) in enumerate(zip(per_judge, softs), 1)]
        score["judge_spread"] = round(max(totals) - min(totals), 1)
        report_soft = "\n\n".join(f"### 评审 {m}\n\n{soft_report(jd)}" for m, jd in enumerate(jdirs, 1))
    score["provenance"] = provenance
    write_json(out_dir / "decisions_compare.json", {
        "items": items, "rulings": rulings, "student_decisions": table,
        **({"rulings_by_judge": rulings_list} if judges > 1 else {}),
        "modules": {"reference": ref_mod, "student": stu_mod}})
    (out_dir / "report.md").write_text(dec.render_report(score, items, rulings, coverage, behaviour, rules,
                                                         tasks, build, report_soft, vocab), encoding="utf-8")
    # Last: a score.json is reused on its own, so the files read beside it must already be there.
    write_json(out_dir / "score.json", score)
    summary = ", ".join(f"{key} {score['dimensions'][key]['score']}" for key in DIMENSIONS)
    judged = f" (judges {', '.join(str(j['total']) for j in score['judges'])})" if judges > 1 else ""
    log(f"{stage}: total {score['total']}{judged} ({summary}); "
        f"code share {score['code_share']['code_share_of_total']:.0%}")
    return score


def score_row(k: int, label: str, data: dict, stu_dir: Path, attempts: int | None) -> dict:
    stu_guards = read_json(stu_dir / "guards.json", {})
    stu_stats = read_json(stu_dir / "stats.json", {})
    usage = stu_stats.get("usage", {})
    return {"iter": k, "sample": label or "-", "total": data["total"],
            **{key: data["dimensions"][key]["score"] for key in DIMENSIONS},
            "judges": score_judges(data), "judge_spread": data.get("judge_spread", ""),
            "code_share": data["code_share"]["code_share_of_total"], "disputes": data["disputes"],
            "gaps_student_wrong": sum(1 for g in data["gaps"] if g["tag"] == "student_wrong"),
            "gaps_high": sum(1 for g in data["gaps"]
                             if g["tag"] == "student_wrong" and g["severity"] == "high"),
            "validate_ok": stu_guards.get("validate", {}).get("ok"),
            "leak_ok": stu_guards.get("leak", {}).get("ok"),
            "no_code_ok": stu_guards.get("no_code", {}).get("ok"),
            "hmos_coverage": stu_stats.get("hmos_coverage"),
            "subagents": stu_stats.get("subagents"),
            "nudges": read_json(stu_dir / "trajectory.run.json", {}).get("nudges", 0),
            "attempts": attempts,
            "input_tokens": usage.get("inputTokens"), "output_tokens": usage.get("outputTokens"),
            "duration_min": round((stu_stats.get("duration_ms") or 0) / 60000, 1),
            "model": stu_stats.get("model_reported")}


def score_or_reuse(run_id: str, state: dict, stage: str, stu_dir: Path, out_dir: Path,
                   judges: int, fresh: bool = False, legacy_ok: bool = False) -> dict | None:
    """Score a sample unless its score.json was produced from the same inputs, student spec,
    reference and judge count; when only the scoring code changed, recompute the aggregate from the
    saved model outputs. With `legacy_ok`, a score without a provenance stamp is reused when its
    judge count matches."""
    old = None if fresh else read_json(out_dir / "score.json")
    provenance = score_provenance(run_id, state, stu_dir, judges)
    mode = reuse_mode(old, provenance)
    if mode == "same" or (mode == "legacy" and legacy_ok and score_judges(old) == judges):
        log(f"reusing {out_dir / 'score.json'}"
            + (" (judged before provenance stamps; its inputs cannot be checked)" if mode == "legacy" else ""))
        return old
    return score_sample(run_id, state, stage, stu_dir, out_dir, reference_decisions(run_id, state),
                        provenance, reuse=mode == "aggregate", judges=judges)


def run_compare_sample(run_id: str, state: dict, k: int, sample: int, samples: int, judges: int,
                       fresh: bool = False) -> tuple[dict, dict | None]:
    """(result for state.json, scores.csv row or None). An invalid or missing student run is not
    scored."""
    sfx = sample_label(state, sample, samples)
    it_dir = iter_dir(run_id, k)
    stu_dir = it_dir / f"student{sfx}"
    out_dir = it_dir / f"compare{sfx}"
    if not student_valid(stu_dir):
        log(f"compare iter {k}{sfx}: the student run is invalid (failed, incomplete, leaked or missing); not scored")
        return {"sample": sfx or "-", "ok": False, "skipped": "invalid student run"}, None
    data = score_or_reuse(run_id, state, f"iter-{k:02d}-compare{sfx}", stu_dir, out_dir, judges, fresh)
    if data is None:
        log(f"compare iter {k}{sfx} FAILED; see {out_dir}")
        return {"sample": sfx or "-", "ok": False}, None
    return ({"sample": sfx or "-", "ok": True, "total": data["total"],
             "judge_totals": [j["total"] for j in data.get("judges", [])]},
            score_row(k, sfx, data, stu_dir, student_attempts(state, k, sfx, stu_dir)))


def cmd_compare(args) -> None:
    """Score every valid sample of an iteration. Invalid student runs are left out and listed;
    when a valid sample fails to score, the iteration gets no score until a re-run succeeds (it
    reuses the samples already scored under the same inputs)."""
    state = load_state(args.run)
    verify_frozen(args.run, state)
    check_inputs_unchanged(args.run, args.allow_drift)
    k = args.iter
    judges = args.judges or CFG.get("judges", 1)
    if not state["iters"].get(str(k), {}).get("student"):
        die(f"iteration {k} has no student runs; run `loop.py student --run {args.run} --iter {k}` first")
    samples = state["iters"][str(k)].get("samples", 1)
    with ThreadPoolExecutor(max_workers=samples) as pool:
        out = [f.result() for f in [pool.submit(run_compare_sample, args.run, state, k, s, samples, judges,
                                                args.fresh)
                                    for s in range(1, samples + 1)]]
    results = [r for r, _row in out]
    csv_path = run_dir(args.run) / "scores.csv"
    rows = [r for r in read_csv(csv_path) if r["iter"] != str(k)] + [row for _r, row in out if row]
    write_csv(csv_path, sorted(rows, key=lambda r: (int(r["iter"]), r["sample"])))
    skipped = [r["sample"] for r in results if r.get("skipped")]
    failed = [r["sample"] for r in results if not r.get("ok") and not r.get("skipped")]
    totals = [r["total"] for r in results if r.get("ok")]
    with state_update(args.run) as state:
        it = state["iters"].setdefault(str(k), {})
        it["compare"] = results
        it["judges"] = judges
        it["score"] = round(statistics.mean(totals), 1) if totals and not failed else None
    if skipped:
        log(f"iteration {k}: {len(skipped)} of {samples} sample(s) left out, the student run is invalid "
            f"({', '.join(skipped)}); the score is the mean of {len(totals)}")
    if failed:
        log(f"iteration {k}: scoring failed for {', '.join(failed)}; no iteration score until "
            f"`compare --iter {k}` succeeds for every valid sample")
    mark_iteration(args.run, state, k)


def cmd_rescore(args) -> None:
    """Score an existing student spec with the current scoring into iter-KK/<out>/; touches
    neither state.json nor scores.csv."""
    state = load_state(args.run)
    verify_frozen(args.run, state)
    rd = run_dir(args.run)
    samples = iteration_samples(args.run, args.iter)
    if not args.student and not samples:
        die(f"iteration {args.iter} has no student sample")
    if re.fullmatch(r"(student|compare)(-s\d+)?|playbook", args.out):
        die(f"--out {args.out} is a directory of the loop itself; pick another name")
    stu_dir = rd / args.student if args.student else samples[0][1]
    out_dir = iter_dir(args.run, args.iter) / args.out
    stu_table = None
    if args.student_decisions:
        stu_table = read_json(rd / args.student_decisions)
        log(f"reusing the student decision table {args.student_decisions}")
    score = score_sample(args.run, state, f"iter-{args.iter:02d}-{args.out}", stu_dir, out_dir,
                         reference_decisions(args.run, state, allow_proposed=True),
                         score_provenance(args.run, state, stu_dir, args.judges), stu_table,
                         reuse=args.reuse, judges=args.judges)
    if score is None:
        die(f"rescore failed; see {out_dir}")
    log(f"rescored {stu_dir.relative_to(rd)}: {out_dir / 'report.md'}")
