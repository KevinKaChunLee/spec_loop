"""synthesize and leak-check: writing and checking the playbook."""

from __future__ import annotations

import shutil

from pathlib import Path

from lib import decisions as dec
from lib import guards, workspace
from lib.common import die, iter_dir, load_state, log, prompt, read_json, run_dir, state_update, write_json
from lib.runner import run_agent

from .core import (CFG, base_dir, hmos_index, model_for, oracle_dir, oracle_spec, reference_decisions,
                   task_text, timeout_for, verify_frozen)
from .provenance import check_inputs_unchanged
from .agents import finish_io_stage, trajviz_stage
from .extraction import extract_playbook
from .marks import iteration_scores, pair_threshold, scored_samples


SYNTH_FIX_PROMPT = """The playbook checker rejected `_outputs/playbook.md`:

{problems}

Passages that overlap with the reference spec (normalized, whitespace and markdown removed):
{spans}

Lines that state a decision AGENTS.md leaves open, state a finding about what the HMOS code does,
or name HMOS identifiers or file names that AGENTS.md, config.yaml and the task do not name:
{leaks}

Rewrite `_outputs/playbook.md` so that it passes: shorten it, replace copied passages and stated answers
with instructions on how to find the information, refer to code by directory or by what to search for
instead of by name, and do not list the reference's capability ids. Flagged lines that remain after the
last rewrite are deleted automatically. Update `_outputs/changelog.md` to match. Do not modify anything else.
"""


def sample_gap_table(run_id: str, state: dict, k: int) -> str | None:
    """Every gap of every scored sample of iteration k, with how many samples share it; None when
    the iteration has fewer than two scored samples."""
    rows: dict[str, dict] = {}
    totals = []
    for label, _s, _c, score in scored_samples(run_id, state, k):
        totals.append((label, score["total"]))
        for g in score.get("gaps", []):
            e = rows.setdefault(g["id"], {"samples": [], "tag": g.get("tag"), "severity": g.get("severity"),
                                          "source": g.get("source", ""), "summary": g.get("summary", "")})
            if label not in e["samples"]:
                e["samples"].append(label)
    if len(totals) < 2:
        return None
    n = len(totals)
    severity = {"high": 0, "medium": 1, "low": 2}
    ordered = sorted(rows.items(), key=lambda kv: (-len(kv[1]["samples"]), kv[1]["tag"] != "student_wrong",
                                                   severity.get(kv[1]["severity"], 3), kv[0]))
    out = ["# Gaps across all samples of this iteration", "",
           f"{n} students received the same prompt: " + ", ".join(f"{label} scored {t}" for label, t in totals) + ".",
           "A gap that most samples share is a systematic weakness; a gap that only one sample has may be chance. "
           "Ids from decisions, coverage and rules (source `decision` or `code`) are the same across samples; "
           "ids the judge wrote (source `judge`) may name the same gap differently.", "",
           "| gap id | samples | tag | severity | source | summary |", "|---|---|---|---|---|---|"]
    for gid, e in ordered:
        summary = str(e["summary"]).replace("|", "\\|").replace("\n", " ")[:240]
        out.append(f"| `{gid}` | {len(e['samples'])}/{n} ({', '.join(e['samples'])}) | {e['tag']} | "
                   f"{e['severity']} | {e['source']} | {summary} |")
    return "\n".join(out) + "\n"


def playbook_base(state: dict, k: int) -> dict:
    """Which playbook the synthesizer revises at iteration k (writing the playbook for k+1).

    Normally the latest one (iter-(k-1), used in iteration k). When iteration k scored below its
    parent, the iteration that used the playbook the latest one was revised from, by more than the
    pair's noise threshold, the revision is taken back: the synthesizer revises the parent playbook
    (none when the parent is iteration 0). One pairwise test against the parent, because the best
    of several noisy earlier scores is biased upward. `based_on` and `reverted_from` are iteration
    indices of playbook directories."""
    keep = {"based_on": k - 1 if k > 0 else None, "reverted_from": None, "reason": ""}
    scores = iteration_scores(state)
    if k == 0 or k not in scores:
        return keep
    parent_pb = state["iters"].get(str(k - 1), {}).get("playbook", {}).get("based_on")
    parent = parent_pb + 1 if parent_pb is not None else 0
    threshold = pair_threshold(state, k, parent)
    if parent not in scores or threshold is None or scores[k] >= scores[parent] - threshold:
        return keep
    return {"based_on": parent_pb, "reverted_from": k - 1,
            "reason": f"{scores[k]}, more than the threshold {threshold} below iteration {parent} "
                      f"({scores[parent]}), which used the playbook the latest one revised"}


def cmd_synthesize(args) -> None:
    state = load_state(args.run)
    verify_frozen(args.run, state)
    check_inputs_unchanged(args.run, args.allow_drift)
    k = args.iter
    if k > 0 and not state.get("noise"):
        log("warning: no noise baseline (`loop.py noise`); a playbook that made scores worse cannot be reverted")
    it = state["iters"].get(str(k), {})
    ok = [r for r in it.get("compare", []) if r.get("ok")]
    if not ok:
        die(f"iteration {k} has no successful comparison; run `loop.py compare --iter {k}` first")
    ok.sort(key=lambda r: r["total"])
    chosen = ok[(len(ok) - 1) // 2]
    sfx = "" if chosen["sample"] == "-" else chosen["sample"]
    it_dir = iter_dir(args.run, k)
    stu_dir, cmp_dir, out_dir = it_dir / f"student{sfx}", it_dir / f"compare{sfx}", it_dir / "playbook"
    out_dir.mkdir(parents=True, exist_ok=True)

    lim = CFG["playbook_limits"]
    tmp = out_dir / "_staging"
    tmp.mkdir(exist_ok=True)
    (tmp / "task.md").write_text(task_text(state), encoding="utf-8")
    (tmp / "playbook_rules.md").write_text(prompt(
        "playbook_rules.md", max_span=str(lim["max_span_chars"]),
        max_total=str(lim["max_total_copied_chars"]),
        cap_share_pct=str(int(lim["max_capability_id_share"] * 100)),
        max_lines=str(lim["max_lines"])), encoding="utf-8")
    inputs = {"task.md": tmp / "task.md", "playbook_rules.md": tmp / "playbook_rules.md",
              "reference": oracle_spec(args.run), "student": stu_dir / "spec",
              "trajectory.md": stu_dir / "trajectory.md", "stats.json": stu_dir / "stats.json",
              "report.md": cmp_dir / "report.md", "score.json": cmp_dir / "score.json"}
    if (run_dir(args.run) / "scores.csv").exists():
        inputs["scores.csv"] = run_dir(args.run) / "scores.csv"
    gap_table = sample_gap_table(args.run, state, k)
    if gap_table:
        (tmp / "sample_gaps.md").write_text(gap_table, encoding="utf-8")
        inputs["sample_gaps.md"] = tmp / "sample_gaps.md"
        log(f"synthesizer gets the gaps of all {len(ok)} samples of iteration {k}; "
            f"report and trajectory from the median sample {chosen['sample']}")
    views_dir = stu_dir / "trajviz" / "trajectory.views"
    if not views_dir.is_dir():
        meta = read_json(stu_dir / "trajectory.run.json", {})
        trajviz_stage(stu_dir, "trajectory", Path(meta.get("workspace", ".")),
                      f"{args.run} student iter {k}{sfx}")
    if views_dir.is_dir():
        picked = tmp / "trajviz"
        picked.mkdir(exist_ok=True)
        for view in CFG.get("trajviz", {}).get("synth_views", []):
            if (views_dir / f"{view}.json").exists():
                shutil.copy2(views_dir / f"{view}.json", picked / f"{view}.json")
        if any(picked.iterdir()):
            inputs["trajviz"] = picked
    base = playbook_base(state, k)
    if base["based_on"] is not None:
        inputs["previous_playbook.md"] = iter_dir(args.run, base["based_on"]) / "playbook" / "playbook.md"
    if base["reverted_from"] is not None:
        inputs["reverted_playbook.md"] = iter_dir(args.run, base["reverted_from"]) / "playbook" / "playbook.md"
        target = "no playbook" if base["based_on"] is None else f"the playbook of iter-{base['based_on']:02d}"
        log(f"iteration {k} scored {base['reason']}; reverting: revising {target} instead of the latest one")
    if k > 0:
        history = [f"## iter-{j:02d}\n\n" + (iter_dir(args.run, j) / "playbook" / "changelog.md")
                   .read_text(encoding="utf-8")
                   for j in range(k) if (iter_dir(args.run, j) / "playbook" / "changelog.md").exists()]
        if history:
            (tmp / "changelog_history.md").write_text("\n\n".join(history), encoding="utf-8")
            inputs["changelog_history.md"] = tmp / "changelog_history.md"

    ws = workspace.build(CFG, args.run, f"iter-{k:02d}-synthesize", inputs)
    sm = model_for(state, "synthesizer")
    meta = run_agent(model=sm, ws=ws, prompt=prompt("synthesize.md"), out_dir=out_dir,
                     label="trajectory", timeout_min=timeout_for(state, "synthesizer"))
    ref_dec = reference_decisions(args.run, state, required=False)
    if ref_dec is None:
        log("warning: no frozen reference decisions; the playbook decision-value check only flags "
            "baseline facts")
    pb = ws / "_outputs" / "playbook.md"
    retries = CFG.get("synth_fix_retries", 0)
    for attempt in range(retries + 1):
        report = playbook_report(args.run, state, pb, ref_dec, out_dir / f"leak-{attempt + 1}",
                                 f"iter-{k:02d}-synthesize-leak{attempt + 1}")
        if report["ok"] or not meta.get("session_id") or attempt == retries:
            break
        problems = report["problems"] + ([f"{len(report['leak_lines'])} line(s) state an open decision or an "
                                          f"HMOS finding, or name HMOS symbols"] if report["leak_lines"] else [])
        log(f"playbook rejected ({'; '.join(problems)}); asking for a rewrite")
        spans = "\n".join(f"- {s}" for s in report.get("spans", [])[:10]) or "- none"
        leaks = "\n".join(f"- line {e['line']}: {e['text'][:160]}  <- {'; '.join(e['reasons'])}"
                          for e in report["leak_lines"][:40]) or "- none"
        meta = run_agent(model=sm, ws=ws, prompt=SYNTH_FIX_PROMPT.format(
            problems="\n".join(f"- {p}" for p in problems), spans=spans, leaks=leaks),
            out_dir=out_dir, label=f"fix{attempt + 1}", timeout_min=timeout_for(state, "synthesizer"),
            resume_session=meta["session_id"])
    stripped = []
    if not report["problems"] and report.get("leak_lines") and pb.exists():
        stripped = report["leak_lines"]
        shutil.copy2(pb, out_dir / "playbook.pre_strip.md")
        pb.write_text(dec.strip_lines(pb.read_text(encoding="utf-8"), [e["line"] for e in stripped]),
                      encoding="utf-8")
        changelog = ws / "_outputs" / "changelog.md"
        note = "\n\n## 泄漏检查自动剔除\n\n" + "\n".join(
            f"- 原第 {e['line']} 行（{'; '.join(e['reasons'])}）：{e['text'][:120]}" for e in stripped) + "\n"
        changelog.write_text((changelog.read_text(encoding="utf-8") if changelog.exists() else "") + note,
                             encoding="utf-8")
        recheck = playbook_report(args.run, state, pb, None, None, None)
        report = {**recheck, "auto_stripped": stripped, "decision_leaks": report["decision_leaks"]}
        log(f"auto-stripped {len(stripped)} flagged line(s) from the playbook")
    write_json(out_dir / "overlap_report.json", report)
    finish_io_stage(args.run, ws, out_dir, ("playbook.md", "changelog.md"), f"synthesizer iter {k}")
    if not report["ok"] and (out_dir / "playbook.md").exists():
        (out_dir / "playbook.md").rename(out_dir / "playbook.rejected.md")
    shutil.rmtree(tmp, ignore_errors=True)
    with state_update(args.run) as state:
        state["iters"].setdefault(str(k), {})["playbook"] = {
            "ok": report["ok"], "problems": report.get("problems", []), "from_sample": chosen["sample"],
            "lines": report.get("lines"), "copied_chars": report.get("copied_chars"),
            "based_on": base["based_on"], "reverted_from": base["reverted_from"],
            "auto_stripped": [{"line": e["line"], "text": e["text"], "reasons": e["reasons"]} for e in stripped]}
    if report["ok"]:
        log(f"playbook for iteration {k + 1} written: {out_dir / 'playbook.md'} ({report['lines']} lines)")
    else:
        log("playbook REJECTED after retries: " + "; ".join(report["problems"] or
                                                            [f"{len(report['leak_lines'])} leak line(s)"]))


def playbook_report(run_id: str, state: dict, playbook: Path, ref_dec: dict | None,
                    out_dir: Path | None, stage: str | None, strict: bool = False,
                    pb_table: dict | None = None) -> dict:
    """Code checks plus the decision-value leak check (extractor on the playbook, compared with the
    reference decisions). `problems` reject the playbook; `leak_lines` can be stripped."""
    index = hmos_index(run_id)
    ref_caps = list(read_json(oracle_dir(run_id) / "metrics.json", {}).get("baseline_capabilities", {}))
    report = guards.check_playbook(CFG, playbook, oracle_spec(run_id), base_dir(run_id), ref_caps,
                                   task_text(state), index)
    dleaks = []
    if playbook.exists():
        if pb_table is None and out_dir is not None:
            pb_table = extract_playbook(run_id, state, playbook, out_dir, stage, f"leak check {stage}")
        if pb_table is not None:
            lines = playbook.read_text(encoding="utf-8", errors="replace").splitlines()
            dleaks = dec.decision_leaks(pb_table, ref_dec or {}, dec.load_vocab(), lines, strict)
    report["decision_leaks"] = dleaks
    report["leak_lines"] = dec.merge_leaks(report.get("symbol_leaks", []), dleaks)
    report["ok"] = not report["problems"] and not report["leak_lines"]
    return report


def cmd_leak_check(args) -> None:
    """Run the playbook checks on an existing playbook (offline: nothing in state changes)."""
    state = load_state(args.run)
    rd = run_dir(args.run)
    pb = (rd / args.playbook) if args.playbook else iter_dir(args.run, args.iter) / "playbook" / "playbook.md"
    if not pb.exists():
        die(f"no playbook at {pb}")
    name = "leak-strict" if args.strict else "leak"
    out_dir = pb.parent / name
    pb_table = read_json(rd / args.decisions) if args.decisions else None
    ref = reference_decisions(args.run, state)
    report = playbook_report(args.run, state, pb, ref, out_dir, f"{pb.parent.parent.name}-{name}",
                             args.strict, pb_table)
    write_json(out_dir / "leak_report.json", report)
    for p in report["problems"]:
        print(f"PROBLEM {p}")
    for e in report["leak_lines"]:
        print(f"line {e['line']:4d}: {'; '.join(e['reasons'])}\n           {e['text'][:150]}")
    print(f"\n{len(report['leak_lines'])} flagged line(s): {[e['line'] for e in report['leak_lines']]}"
          f"  (decision: {sorted({e['line'] for e in report['decision_leaks']})}, "
          f"symbol: {[e['line'] for e in report['symbol_leaks']]})")
    if args.write_stripped:
        dst = out_dir / "playbook.stripped.md"
        dst.write_text(dec.strip_lines(pb.read_text(encoding="utf-8"),
                                       [e["line"] for e in report["leak_lines"]]), encoding="utf-8")
        log(f"stripped playbook: {dst}")
