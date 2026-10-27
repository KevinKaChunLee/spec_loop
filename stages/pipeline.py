"""iterate, reset, status, trajviz and smoke."""

from __future__ import annotations

import argparse
import sys

from pathlib import Path

from lib.common import die, iter_dir, load_state, log, read_json, remove_tree, run_dir, state_update

from .core import (CFG, CONSENSUS_FILE, DIMENSIONS, manifest_text, oracle_dir, oracle_runs, oracle_spec, read_csv,
                   sample_label, smoke, verify_frozen, write_csv)
from .provenance import check_inputs_unchanged, spec_digest
from .agents import run_labels, trajviz_stage
from .oracle import cmd_oracle, cmd_prepare
from .student import cmd_student, stale_students, student_prompt
from .marks import best_playbook_iter, change_vs_best, iteration_scores, scored_count, scored_samples
from .scoring import cmd_compare
from .synthesis import cmd_synthesize


def ensure_playbook(run_id: str, k: int, allow_drift: bool) -> None:
    if not load_state(run_id)["iters"].get(str(k), {}).get("playbook", {}).get("ok"):
        cmd_synthesize(argparse.Namespace(run=run_id, iter=k, allow_drift=allow_drift))
        if not load_state(run_id)["iters"][str(k)].get("playbook", {}).get("ok"):
            die(f"iteration {k}: no acceptable playbook; inspect {iter_dir(run_id, k) / 'playbook'}")


def stale_scores(run_id: str, state: dict, k: int) -> list[str]:
    """Scored samples of iteration k whose score.json was produced from another student spec than
    the one on disk (scores without a provenance stamp are not checked)."""
    return [label for label, s, c, sc in scored_samples(run_id, state, k)
            if sc.get("provenance") and sc["provenance"]["student_spec"] != spec_digest(s / "spec")]


def cmd_iterate(args) -> None:
    """Run a fixed number of iterations (no early stop): student -> compare -> synthesize. The last
    iteration writes no playbook; a later `iterate --start` writes it first."""
    state = load_state(args.run)
    verify_frozen(args.run, state)
    allow = args.allow_drift
    check_inputs_unchanged(args.run, allow)
    judges = args.judges or CFG.get("judges", 1)
    last = args.start + (args.iters or CFG["iterations"]) - 1
    if last >= 1 and not state.get("noise"):
        log("warning: no noise baseline yet (`loop.py noise` after iteration 0): score changes are not "
            "marked, and a playbook that made scores worse is never reverted")
    for k in range(args.start, last + 1):
        if k > 0:
            ensure_playbook(args.run, k - 1, allow)
        state = load_state(args.run)
        it = state["iters"].get(str(k), {})
        if any(r.get("valid") for r in it.get("student", [])):
            stale = stale_students(args.run, k, student_prompt(state, args.run, k))
            if stale:
                die(f"iteration {k}: sample(s) {', '.join(stale)} were run with another prompt than iteration {k}'s "
                    f"current one (did its playbook change?); discard them with "
                    f"`loop.py reset --run {args.run} --from-iter {k}`")
        else:
            cmd_student(argparse.Namespace(run=args.run, iter=k, samples=args.samples, dry_run=False,
                                           allow_drift=allow))
            state = load_state(args.run)
            if not any(r.get("valid") for r in state["iters"][str(k)]["student"]):
                die(f"iteration {k}: no valid student run; inspect {iter_dir(args.run, k)}")
        stale = stale_scores(args.run, state, k)
        if stale:
            log(f"iteration {k}: the scores of {', '.join(stale)} belong to another student spec; scoring again")
        if state["iters"][str(k)].get("score") is None or stale:
            cmd_compare(argparse.Namespace(run=args.run, iter=k, judges=judges, fresh=False, allow_drift=allow))
            state = load_state(args.run)
            if state["iters"][str(k)].get("score") is None:
                die(f"iteration {k}: comparison failed; inspect {iter_dir(args.run, k)}")
        if k < last:
            ensure_playbook(args.run, k, allow)
    state = load_state(args.run)
    best = best_playbook_iter(state)
    log(f"finished iterations {args.start}..{last}" + (
        f"; highest raw score with a playbook: iteration {best} ({iteration_scores(state)[best]}), playbook "
        f"{iter_dir(args.run, best - 1) / 'playbook' / 'playbook.md'}; `loop.py ablate` tests whether it helps"
        if best is not None else ""))


def cmd_reset(args) -> None:
    with state_update(args.run) as state:
        gone = sorted(int(k) for k in state["iters"] if int(k) >= args.from_iter)
        for k in gone:
            del state["iters"][str(k)]
    for k in gone:
        remove_tree(iter_dir(args.run, k))
    csv_path = run_dir(args.run) / "scores.csv"
    if csv_path.exists():
        write_csv(csv_path, [r for r in read_csv(csv_path) if int(r["iter"]) < args.from_iter])
    log(f"discarded iterations {gone or 'none'} of run '{args.run}'")


def cmd_status(args) -> None:
    state = load_state(args.run)
    o = state["oracle"]
    print(f"run {args.run}{' (smoke)' if smoke(state) else ''}")
    print(f"  oracle: {o.get('status')}  frozen={state.get('frozen')}"
          + (f"  validate={o['validate_ok']}" if "validate_ok" in o else "")
          + (f"  reference spec of {o['medoid']}" if o.get("medoid") else ""))
    for label, od in oracle_runs(args.run, state):
        r = read_json(od / "oracle.json")
        if r:
            print(f"    {label}: {'valid' if r['valid'] else 'INVALID'}  repairs={r['repairs']}  attempts={r['attempts']}"
                  + (f"  AGENTS.md conflicts left: {', '.join(r['contradictions'])}" if r["contradictions"] else "")
                  + (f"  problems: {'; '.join(r['problems'])}" if r["problems"] else ""))
    if state.get("reference_decisions"):
        rdec = state["reference_decisions"]
        consensus = read_json(oracle_dir(args.run) / CONSENSUS_FILE)
        print(f"  reference decisions: frozen={rdec.get('frozen')}  stated={rdec.get('stated')}"
              + (f"  without a majority={len(consensus['contested'])}  set to AGENTS.md={len(consensus['overrides'])}"
                 if consensus else "")
              + (f"  copied from {rdec['copied_from']}" if rdec.get("copied_from") else ""))
    for d in state.get("drift", []):
        print(f"  accepted input drift ({d['at']}): {'; '.join(d['changed'])}")
    noise = state.get("noise")
    if noise:
        print(f"  noise (iteration {noise['iter']}, {noise['samples']} samples x {noise['judges']} judges): "
              f"sigma_judge {noise['sigma_judge']}  sigma_student {noise['sigma_student']}  "
              f"sigma_iteration {noise['sigma_iteration']}  threshold {noise['threshold']} (1 sample vs 1 sample)"
              + (f"  sigma_extract <= {noise['sigma_extract_bound']}" if noise.get("sigma_extract_bound") is not None
                 else ""))
        if "var_student" not in noise:
            print(f"  this noise baseline predates the current student variance, so iterations are not marked; "
                  f"`loop.py noise --run {args.run} --extract-passes 1` measures it again without agent runs")
    for k in sorted(state["iters"], key=int):
        it = state["iters"][k]
        st = ", ".join(f"{r['sample']}:{'valid' if r.get('valid') else 'INVALID'}"
                       for r in it.get("student", []))
        pb = it.get("playbook", {})
        vs = change_vs_best(state, int(k))
        mark = (f"  vs best {vs['delta']:+.1f}" + (f" {vs['mark']} (threshold {vs['threshold']})" if vs["mark"] else "")
                if vs else "")
        counted = f" (n={scored_count(it)}, J={it.get('judges', 1)})" if it.get("score") is not None else ""
        skipped = [r["sample"] for r in it.get("compare", []) if r.get("skipped")]
        left = f"  left out: {', '.join(skipped)}" if skipped else ""
        based = f" (based on iter-{pb['based_on']:02d})" if pb.get("based_on") is not None else ""
        reverted = f", reverted from iter-{pb['reverted_from']:02d}" if pb.get("reverted_from") is not None else ""
        stripped = f", {len(pb['auto_stripped'])} line(s) auto-stripped" if pb.get("auto_stripped") else ""
        print(f"  iter {int(k):02d}: student [{st}]  score={it.get('score')}{counted}{mark}{left}  "
              f"playbook={'ok' if pb.get('ok') else ('rejected' if pb else '-')}{based}{reverted}{stripped}")
    rows = read_csv(run_dir(args.run) / "scores.csv")
    cols = ("iter", "sample", "total", "vs_best", *DIMENSIONS, "judge_spread", "gaps_closed", "gaps_reopened")
    if rows:
        print("\n  " + "  ".join(cols))
        for r in rows:
            print("  " + "  ".join(str(r.get(c, "")) for c in cols))
    abl = read_json(run_dir(args.run) / "ablation" / "ablation.json")
    if abl:
        print("\n  ablation (" + abl["playbook"] + "): " + "  ".join(
            f"{a} {v['mean']} (n={v['n']})" for a, v in abl["arms"].items()))
        for p in abl["pairs"]:
            test = (f"Welch t {p['t']}, df {p['df']}, critical difference {p['critical_diff']}, p {p['p']}"
                    if "critical_diff" in p else f"2 SE {p.get('two_se')}")
            print(f"    {p['a']} - {p['b']}{' (primary)' if p.get('primary') else ''}: {p['diff']:+.1f} ({test}) "
                  f"{'significant' if p['significant'] else 'not significant'}")


def cmd_trajviz(args) -> None:
    rd = run_dir(args.run)
    stages = [rd / args.stage] if args.stage else \
        sorted({p.parent for p in rd.rglob("*.run.json") if "transcripts" not in p.parts})
    for out_dir in stages:
        for label in run_labels(out_dir):
            meta = read_json(out_dir / f"{label}.run.json", {})
            title = f"{args.run} {out_dir.relative_to(rd).as_posix()} ({label})"
            trajviz_stage(out_dir, label, Path(meta.get("workspace", ".")), title)
            html = out_dir / "trajviz" / f"{label}.html"
            log(f"{out_dir.relative_to(rd)}/{label}: {out_dir / 'trajviz' / (label + '.trajviz.json')}"
                + (f"  report: {html}" if html.exists() else ""))


def cmd_smoke(args) -> None:
    if not (run_dir(args.run) / "state.json").exists():
        cmd_prepare(argparse.Namespace(run=args.run, force=False, smoke=True, reference_from=None,
                                       allow_drift=False))
    state = load_state(args.run)
    if not smoke(state):
        die(f"run '{args.run}' is not a smoke run")
    if not state.get("frozen"):
        cmd_oracle(argparse.Namespace(run=args.run, allow_drift=False))
    verify_frozen(args.run, load_state(args.run))
    if not load_state(args.run)["iters"].get("0", {}).get("student"):
        cmd_student(argparse.Namespace(run=args.run, iter=0, samples=1, dry_run=False, allow_drift=False))
    if load_state(args.run)["iters"]["0"].get("score") is None:
        cmd_compare(argparse.Namespace(run=args.run, iter=0, judges=1, fresh=False, allow_drift=False))
    if not load_state(args.run)["iters"]["0"].get("playbook"):
        cmd_synthesize(argparse.Namespace(run=args.run, iter=0, allow_drift=False))

    state = load_state(args.run)
    checks = []
    rd = run_dir(args.run)
    sfx = sample_label(state, 1, 1)
    oracles = [od.relative_to(rd).as_posix() for _label, od in oracle_runs(args.run, state)]
    for stage in (*oracles, f"iter-00/student{sfx}", f"iter-00/compare{sfx}/decisions",
                  f"iter-00/compare{sfx}/soft", "iter-00/playbook"):
        meta = read_json(rd / stage / "trajectory.run.json", {})
        checks.append((f"{stage}: model reported '{meta.get('model_reported')}'", meta.get("model_ok")))
        checks.append((f"{stage}: run finished", meta.get("has_result") and not meta.get("is_error")))
        checks.append((f"{stage}: transcript copied", bool(meta.get("transcript_copy"))))
        checks.append((f"{stage}: trajectory.md rendered", (rd / stage / "trajectory.md").exists()))
    for stage in (*oracles, f"iter-00/student{sfx}"):
        g = read_json(rd / stage / "guards.json", {})
        checks.append((f"{stage}: only openspec/ written", g.get("no_code", {}).get("ok")))
        checks.append((f"{stage}: openspec validate", g.get("validate", {}).get("ok")))
        checks.append((f"{stage}: leak-free", g.get("leak", {}).get("ok")))
    for stage in oracles:
        checks.append((f"{stage}: two extractions agreed into decisions/agreed.json",
                       (rd / stage / "decisions" / "agreed.json").exists()))
    medoid = state["oracle"].get("medoid")
    consensus = read_json(oracle_dir(args.run) / CONSENSUS_FILE, {})
    checks.append((f"consensus of {len(oracles)} oracles written ({consensus.get('stated')} decisions, "
                   f"{len(consensus.get('names', []))} coverage names)", bool(consensus)))
    checks.append((f"reference spec is the medoid's ({medoid})", bool(medoid) and
                   manifest_text(oracle_spec(args.run)) == manifest_text(oracle_dir(args.run) / medoid / "spec")))
    checks.append(("reference frozen and manifest verified", state.get("frozen")))
    checks.append(("reference decisions frozen", state.get("reference_decisions", {}).get("frozen")))
    checks.append(("score.json valid and scored", state["iters"]["0"].get("score") is not None))
    checks.append(("playbook accepted", state["iters"]["0"].get("playbook", {}).get("ok")))
    if state["iters"]["0"].get("playbook", {}).get("ok"):
        text = student_prompt(state, args.run, 1)
        checks.append((f"iteration-1 prompt includes the playbook ({len(text.encode('utf-8'))} bytes)",
                       "# Playbook" in text))
    print("\nsmoke checks:")
    for label, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not all(ok for _, ok in checks):
        sys.exit(2)
