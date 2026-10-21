#!/usr/bin/env python3
"""Oracle / student OpenSpec loop driven by the Cursor CLI.

Typical flow:
  loop.py prepare --run r1
  loop.py oracle  --run r1                   # oracle writes the reference spec
  # review runs/r1/oracle/spec/openspec/: edit it directly, and/or
  loop.py oracle  --run r1 --revise "..."    # resume the oracle session with feedback
  loop.py freeze  --run r1                   # hash + make read-only; never changes again
  loop.py iterate --run r1 --iters 3         # student -> compare -> synthesize, repeated
  loop.py status  --run r1

Single stages: `student`, `compare`, `synthesize` (all take --iter K).
`student --iter 0` may run before the freeze, since it needs nothing from the oracle.

Plumbing test with a tiny task and the smoke model for every role:
  loop.py smoke --run smoke1
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import shutil
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from lib import guards, render_traj, spec_metrics, workspace
from lib.common import (PROMPTS, ROOT, copy_tree, die, iter_dir, load_config, load_state, log,
                        make_readonly, make_writable, prompt, read_json, run_dir, sample_suffix,
                        save_state, sha256_bytes, sha256_file, write_json)
from lib.runner import run_agent

CFG = load_config()
DIMENSIONS = list(CFG["rubric_weights"])
SEVERITIES = {"high", "medium", "low"}
TAGS = {"student_wrong", "student_defensible", "reference_questionable"}
CSV_FIELDS = ["iter", "sample", "total", *DIMENSIONS, "gaps_student_wrong", "gaps_high",
              "validate_ok", "leak_ok", "no_code_ok", "hmos_coverage", "subagents",
              "input_tokens", "output_tokens", "duration_min", "model"]

REVISE_PROMPT = """A human reviewer read the OpenSpec you wrote in this workspace and asks for the changes below.
The files under openspec/ may also contain edits the reviewer made directly; keep those.
Apply the feedback, keep every rule of the original task (write only under openspec/, no questions,
zh-CN prose), and finish only when `openspec validate --all --strict` passes.

Reviewer feedback:

{feedback}
"""

JUDGE_FIX_PROMPT = """`_outputs/score.json` does not match the required schema:

{errors}

Fix `_outputs/score.json` (and `_outputs/report.md` if the scores change). Do not modify anything else.
"""

SYNTH_FIX_PROMPT = """The playbook checker rejected `_outputs/playbook.md`:

{problems}

Passages that overlap with the reference spec (normalized, whitespace and markdown removed):
{spans}

Rewrite `_outputs/playbook.md` so that it passes: shorten it, replace copied passages with instructions on
how to find the information, and do not list the reference's capability ids. Update `_outputs/changelog.md`
to match. Do not modify anything else.
"""


# ---------------------------------------------------------------- helpers

def smoke(state: dict) -> bool:
    return bool(state.get("smoke"))


def model_for(state: dict, role: str) -> dict:
    return CFG["smoke_model"] if smoke(state) else CFG["models"][role]


def timeout_for(state: dict, role: str) -> float:
    return CFG["timeouts_min"]["smoke"] if smoke(state) else CFG["timeouts_min"][role]


def task_text(state: dict) -> str:
    name = "smoke_task.md" if smoke(state) else "task.md"
    return prompt(name, change_name=CFG["change_name"])


def base_dir(run_id: str) -> Path:
    return run_dir(run_id) / "base"


def hmos_index(run_id: str) -> dict:
    return spec_metrics.build_hmos_index(base_dir(run_id), CFG["hmos_dir"],
                                         run_dir(run_id) / "hmos_index.json")


def oracle_dir(run_id: str) -> Path:
    return run_dir(run_id) / "oracle"


def oracle_spec(run_id: str) -> Path:
    return oracle_dir(run_id) / "spec"


def manifest_text(spec_root: Path) -> str:
    lines = [f"{sha256_file(p)}  {p.relative_to(spec_root).as_posix()}"
             for p in sorted(spec_root.rglob("*")) if p.is_file()]
    return "\n".join(lines) + "\n"


def verify_frozen(run_id: str, state: dict) -> None:
    if not state.get("frozen"):
        die("the oracle spec is not frozen yet; review it and run `loop.py freeze`")
    manifest = oracle_dir(run_id) / "MANIFEST.sha256"
    if manifest_text(oracle_spec(run_id)) != manifest.read_text(encoding="utf-8"):
        die(f"the frozen oracle spec changed since freeze ({manifest}); restore it before continuing")


def check_inputs_unchanged(run_id: str) -> None:
    lock = read_json(run_dir(run_id) / "inputs.lock.json", {})
    changed = [name for name, digest in lock.get("prompts", {}).items()
               if (ROOT / name).exists() and sha256_file(ROOT / name) != digest]
    if changed:
        log(f"warning: prompts changed since prepare ({', '.join(changed)}); "
            f"scores may not be comparable with earlier iterations")


def tool_version(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, timeout=60).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"


def post_spec_stage(run_id: str, ws: Path, out_dir: Path, labels: list[str], title: str) -> dict:
    """Copy openspec/ out of the workspace, run guards, render trajectories, compute metrics."""
    spec_root = out_dir / "spec"
    copy_tree(ws / "openspec", spec_root / "openspec")
    transcripts = out_dir / "transcripts"
    meta = read_json(out_dir / f"{labels[-1]}.run.json", {})
    result = {
        "no_code": guards.no_code(ws, ("openspec/",)),
        "validate": guards.validate(spec_root),
        "leak": {"ok": True, "violations": [], "warnings": []},
    }
    for label in labels:
        leak = guards.leak_check(CFG, ws, out_dir / f"{label}.jsonl", transcripts / label,
                                 meta.get("transcript_project"), ROOT, run_dir(run_id))
        result["leak"]["ok"] &= leak["ok"]
        result["leak"]["violations"] += leak["violations"]
        result["leak"]["warnings"] += leak["warnings"]
        suffix = "" if label == "trajectory" else f".{label}"
        render_traj.render(out_dir / f"{label}.jsonl", ws, out_dir / f"trajectory{suffix}.md",
                           out_dir / f"stats{suffix}.json", CFG, CFG["hmos_dir"],
                           transcripts / label, title=f"{title} ({label})")
    write_json(out_dir / "guards.json", result)
    metrics = spec_metrics.collect(spec_root, base_dir(run_id), CFG, hmos_index(run_id))
    write_json(out_dir / "metrics.json", metrics)
    log(f"guards: only-openspec={result['no_code']['ok']} validate={result['validate']['ok']} "
        f"leak-free={result['leak']['ok']}; baseline capabilities="
        f"{metrics['baseline_totals']['capabilities']}, change exists={metrics['change_exists']}")
    for v in result["leak"]["violations"][:5]:
        log(f"  LEAK {v['tool']} {v['path']} ({v['reason']})")
    for p in result["no_code"]["violations"][:5]:
        log(f"  wrote outside openspec/: {p}")
    return result


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
    path.write_text(buf.getvalue(), encoding="utf-8")


# ---------------------------------------------------------------- prepare / oracle / freeze

def cmd_prepare(args) -> None:
    rd = run_dir(args.run)
    if (rd / "state.json").exists() and not args.force:
        die(f"run '{args.run}' already exists (use --force to re-prepare)")
    rd.mkdir(parents=True, exist_ok=True)
    if base_dir(args.run).exists():
        make_writable(base_dir(args.run))
        shutil.rmtree(base_dir(args.run))
    workspace.extract(CFG, base_dir(args.run))
    repo, sha = CFG["repo"], CFG["base_sha"]

    def blob(path: str) -> str:
        return sha256_bytes(subprocess.run(["git", "-C", repo, "show", f"{sha}:{path}"],
                                           stdout=subprocess.PIPE, check=True).stdout)

    skills = {p.parent.name: sha256_file(p)
              for p in sorted(Path(CFG["cursor_dir"]).glob("skills/openspec-*/SKILL.md"))}
    prompt_files = ["rubric.md", *[f"prompts/{p.name}" for p in sorted(PROMPTS.glob("*.md"))]]
    lock = {
        "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "base_sha": sha,
        "files": {p: blob(p) for p in ("AGENTS.md", "openspec/config.yaml")},
        "hmos_tree": subprocess.run(["git", "-C", repo, "rev-parse", f"{sha}:{CFG['hmos_dir']}"],
                                    stdout=subprocess.PIPE, text=True, check=True).stdout.strip(),
        "skills": skills,
        "prompts": {p: sha256_file(ROOT / p) for p in prompt_files},
        "config": sha256_file(ROOT / "config.json"),
        "models": {"smoke": CFG["smoke_model"]} if args.smoke else CFG["models"],
        "agent_cli": tool_version(["agent", "--version"]),
        "openspec_cli": tool_version(["openspec", "--version"]),
        "smoke": bool(args.smoke),
    }
    write_json(rd / "inputs.lock.json", lock)
    if (rd / "hmos_index.json").exists():
        (rd / "hmos_index.json").unlink()
    hmos_index(args.run)
    save_state(args.run, {"run": args.run, "smoke": bool(args.smoke),
                          "oracle": {"status": "pending"}, "frozen": False, "iters": {}})
    log(f"prepared run '{args.run}' at {rd} (base {sha[:12]}{', smoke' if args.smoke else ''})")


def cmd_oracle(args) -> None:
    state = load_state(args.run)
    if state.get("frozen"):
        die("the oracle spec is frozen; it cannot be regenerated or revised")
    od = oracle_dir(args.run)
    om = model_for(state, "oracle")
    ostate = state["oracle"]
    feedback = args.revise
    if args.revise_file:
        feedback = Path(args.revise_file).read_text(encoding="utf-8")

    if feedback is None:
        ws = workspace.build(CFG, args.run, "oracle")
        labels = ["trajectory"]
        meta = run_agent(model=om, ws=ws, prompt=task_text(state), out_dir=od, label="trajectory",
                         timeout_min=timeout_for(state, "oracle"))
    else:
        if ostate.get("status") in (None, "pending") or not ostate.get("session_id"):
            die("there is no oracle session to revise; run `loop.py oracle` first")
        ws = Path(ostate["workspace"])
        copy = oracle_spec(args.run) / "openspec"
        if copy.exists() and manifest_text(copy) != manifest_text(ws / "openspec"):
            log("syncing reviewer edits from runs/.../oracle/spec into the oracle workspace")
            make_writable(ws / "openspec")
            copy_tree(copy, ws / "openspec")
        labels = ostate.get("labels", ["trajectory"])
        label = f"revise{sum(1 for x in labels if x.startswith('revise')) + 1}"
        labels = [*labels, label]
        meta = run_agent(model=om, ws=ws, prompt=REVISE_PROMPT.format(feedback=feedback.strip()),
                         out_dir=od, label=label, timeout_min=timeout_for(state, "oracle"),
                         resume_session=ostate["session_id"])

    result = post_spec_stage(args.run, ws, od, labels, "oracle")
    fatal = []
    if not meta["ok"]:
        fatal.append("the agent run did not finish cleanly (see the .run.json)")
    if not result["no_code"]["ok"]:
        fatal.append("files were written outside openspec/")
    if not result["leak"]["ok"]:
        fatal.append("the trajectory touched forbidden paths")
    state = load_state(args.run)
    state["oracle"] = {
        "status": "failed" if fatal else "awaiting-review",
        "problems": fatal,
        "session_id": meta.get("session_id") or ostate.get("session_id"),
        "workspace": str(ws),
        "labels": labels,
        "validate_ok": result["validate"]["ok"],
    }
    save_state(args.run, state)
    if fatal:
        log("oracle run FAILED: " + "; ".join(fatal))
    else:
        log(f"oracle spec ready for review: {oracle_spec(args.run) / 'openspec'}")
        if not result["validate"]["ok"]:
            log("note: `openspec validate --all --strict` fails; see oracle/guards.json")
        log("next: edit the spec directly and/or `loop.py oracle --revise ...`, then `loop.py freeze`")


def cmd_freeze(args) -> None:
    state = load_state(args.run)
    if state.get("frozen"):
        log("already frozen")
        verify_frozen(args.run, state)
        return
    if state["oracle"].get("status") != "awaiting-review" and not args.force:
        die(f"oracle status is '{state['oracle'].get('status')}'; only a reviewed spec can be frozen "
            f"(use --force to override)")
    spec_root = oracle_spec(args.run)
    v = guards.validate(spec_root)
    if not v["ok"] and not args.force:
        die("`openspec validate --all --strict` fails on the oracle spec:\n" +
            json.dumps(v.get("failed") or v.get("error"), ensure_ascii=False, indent=2) +
            "\nfix it (edit or --revise) or pass --force")
    metrics = spec_metrics.collect(spec_root, base_dir(args.run), CFG, hmos_index(args.run))
    write_json(oracle_dir(args.run) / "metrics.json", metrics)
    guards_path = oracle_dir(args.run) / "guards.json"
    g = read_json(guards_path, {})
    g["validate"] = v
    write_json(guards_path, g)
    (oracle_dir(args.run) / "MANIFEST.sha256").write_text(manifest_text(spec_root), encoding="utf-8")
    make_readonly(spec_root)
    state["frozen"] = True
    state["frozen_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    state["oracle"]["status"] = "frozen"
    save_state(args.run, state)
    log(f"oracle spec frozen ({sum(1 for p in spec_root.rglob('*') if p.is_file())} files); "
        f"manifest at {oracle_dir(args.run) / 'MANIFEST.sha256'}")


# ---------------------------------------------------------------- student

def student_prompt(state: dict, run_id: str, k: int) -> str:
    text = task_text(state)
    if k == 0:
        return text
    pb = iter_dir(run_id, k - 1) / "playbook" / "playbook.md"
    if not pb.exists():
        die(f"iteration {k} needs the playbook from iteration {k - 1}: {pb} is missing")
    return (text.rstrip() + "\n\n---\n\n# Playbook\n\n"
            "The playbook below comes from earlier attempts at this same task. Follow it.\n\n" +
            pb.read_text(encoding="utf-8").strip() + "\n")


def run_student_sample(run_id: str, state: dict, k: int, sample: int, samples: int,
                       text: str) -> dict:
    sfx = sample_suffix(sample, samples)
    out_dir = iter_dir(run_id, k) / f"student{sfx}"
    attempts = CFG.get("student_retries", 0) + 1
    for attempt in range(1, attempts + 1):
        ws = workspace.build(CFG, run_id, f"iter-{k:02d}-student{sfx}")
        meta = run_agent(model=model_for(state, "student"), ws=ws, prompt=text, out_dir=out_dir,
                         label="trajectory", timeout_min=timeout_for(state, "student"))
        result = post_spec_stage(run_id, ws, out_dir, ["trajectory"], f"student iter {k}{sfx}")
        valid = meta["ok"] and result["leak"]["ok"]
        if valid or attempt == attempts:
            break
        log(f"student iter {k}{sfx}: invalid run (agent ok={meta['ok']}, "
            f"leak-free={result['leak']['ok']}); retrying ({attempt}/{attempts - 1})")
    return {"sample": sfx or "-", "valid": valid, "agent_ok": meta["ok"],
            "leak_ok": result["leak"]["ok"], "no_code_ok": result["no_code"]["ok"],
            "validate_ok": result["validate"]["ok"], "session_id": meta.get("session_id"),
            "workspace": str(ws), "attempts": attempt}


def cmd_student(args) -> None:
    state = load_state(args.run)
    k = args.iter
    if k > 0 or state.get("frozen"):
        verify_frozen(args.run, state)
    check_inputs_unchanged(args.run)
    text = student_prompt(state, args.run, k)
    if args.dry_run:
        print(text)
        log(f"prompt: {len(text.encode('utf-8'))} bytes")
        return
    samples = max(1, args.samples)
    with ThreadPoolExecutor(max_workers=samples) as pool:
        futures = [pool.submit(run_student_sample, args.run, state, k, s, samples, text)
                   for s in range(1, samples + 1)]
        results = [f.result() for f in futures]
    state = load_state(args.run)
    it = state["iters"].setdefault(str(k), {})
    it["samples"] = samples
    it["student"] = results
    save_state(args.run, state)
    for r in results:
        log(f"student iter {k} sample {r['sample']}: valid={r['valid']} validate={r['validate_ok']} "
            f"only-openspec={r['no_code_ok']}")


# ---------------------------------------------------------------- compare

def check_score(data) -> list[str]:
    errors = []
    if not isinstance(data, dict):
        return ["top level must be an object"]
    dims = data.get("dimensions")
    if not isinstance(dims, dict):
        errors.append("missing object 'dimensions'")
        dims = {}
    for key in DIMENSIONS:
        entry = dims.get(key)
        if not isinstance(entry, dict):
            errors.append(f"dimensions.{key} is missing")
            continue
        s = entry.get("score")
        if not isinstance(s, int) or isinstance(s, bool) or not 0 <= s <= 5:
            errors.append(f"dimensions.{key}.score must be an integer 0-5 (got {s!r})")
    gaps = data.get("gaps")
    if not isinstance(gaps, list):
        errors.append("missing list 'gaps'")
        gaps = []
    for i, g in enumerate(gaps):
        if not isinstance(g, dict):
            errors.append(f"gaps[{i}] must be an object")
            continue
        for field in ("id", "summary"):
            if not isinstance(g.get(field), str) or not g.get(field):
                errors.append(f"gaps[{i}].{field} is missing")
        if g.get("dimension") not in DIMENSIONS:
            errors.append(f"gaps[{i}].dimension must be one of {DIMENSIONS}")
        if g.get("severity") not in SEVERITIES:
            errors.append(f"gaps[{i}].severity must be one of {sorted(SEVERITIES)}")
        if g.get("tag") not in TAGS:
            errors.append(f"gaps[{i}].tag must be one of {sorted(TAGS)}")
    return errors[:30]


def weighted_total(data: dict) -> float:
    w = CFG["rubric_weights"]
    return round(sum(data["dimensions"][k]["score"] / 5 * w[k] for k in w) / sum(w.values()) * 100, 1)


def run_compare_sample(run_id: str, state: dict, k: int, sample: int, samples: int) -> dict:
    sfx = sample_suffix(sample, samples)
    it_dir = iter_dir(run_id, k)
    stu_dir = it_dir / f"student{sfx}"
    out_dir = it_dir / f"compare{sfx}"
    if not (stu_dir / "spec").exists():
        die(f"no student spec for iteration {k}{sfx}; run `loop.py student --iter {k}` first")
    index = hmos_index(run_id)
    ref_m = spec_metrics.collect(oracle_spec(run_id), base_dir(run_id), CFG, index)
    stu_m = read_json(stu_dir / "metrics.json") or \
        spec_metrics.collect(stu_dir / "spec", base_dir(run_id), CFG, index)
    d = spec_metrics.diff(ref_m, stu_m)
    out_dir.mkdir(parents=True, exist_ok=True)
    md = spec_metrics.render_md(ref_m, stu_m, d, read_json(oracle_dir(run_id) / "guards.json", {}),
                                read_json(stu_dir / "guards.json", {}))
    (out_dir / "metrics.md").write_text(md, encoding="utf-8")
    write_json(out_dir / "metrics_diff.json", d)

    tmp = out_dir / "_staging"
    tmp.mkdir(exist_ok=True)
    (tmp / "task.md").write_text(task_text(state), encoding="utf-8")
    inputs = {"task.md": tmp / "task.md", "rubric.md": ROOT / "rubric.md",
              "reference": oracle_spec(run_id), "student": stu_dir / "spec",
              "metrics.md": out_dir / "metrics.md"}
    prev = it_dir.parent / f"iter-{k - 1:02d}" / f"compare{sfx}" / "score.json"
    if not prev.exists():
        prev = it_dir.parent / f"iter-{k - 1:02d}" / "compare" / "score.json"
    if k > 0 and prev.exists():
        gaps = [{"id": g.get("id"), "summary": g.get("summary")}
                for g in (read_json(prev, {}) or {}).get("gaps", [])]
        write_json(tmp / "previous_gaps.json", gaps)
        inputs["previous_gaps.json"] = tmp / "previous_gaps.json"

    ws = workspace.build(CFG, run_id, f"iter-{k:02d}-compare{sfx}", inputs)
    jm = model_for(state, "judge")
    meta = run_agent(model=jm, ws=ws, prompt=prompt("compare.md", change_name=CFG["change_name"]),
                     out_dir=out_dir, label="trajectory", timeout_min=timeout_for(state, "judge"))
    errors, data = ["_outputs/score.json was not written"], None
    for attempt in range(CFG.get("judge_fix_retries", 0) + 1):
        sp = ws / "_outputs" / "score.json"
        if sp.exists():
            try:
                data = json.loads(sp.read_text(encoding="utf-8"))
                errors = check_score(data)
            except json.JSONDecodeError as e:
                errors = [f"invalid JSON: {e}"]
        if not errors or not meta.get("session_id") or attempt == CFG.get("judge_fix_retries", 0):
            break
        log(f"score.json invalid ({len(errors)} problems); asking the judge to fix it")
        meta = run_agent(model=jm, ws=ws, prompt=JUDGE_FIX_PROMPT.format(errors="\n".join(
            f"- {e}" for e in errors)), out_dir=out_dir, label=f"fix{attempt + 1}",
            timeout_min=timeout_for(state, "judge"), resume_session=meta["session_id"])
    for name in ("score.json", "report.md"):
        if (ws / "_outputs" / name).exists():
            (out_dir / name).write_bytes((ws / "_outputs" / name).read_bytes())
    render_traj.render(out_dir / "trajectory.jsonl", ws, out_dir / "trajectory.md",
                       out_dir / "stats.json", CFG, CFG["hmos_dir"], out_dir / "transcripts" / "trajectory",
                       title=f"judge iter {k}{sfx}")
    write_json(out_dir / "guards.json", {"no_code": guards.no_code(ws, ("_outputs/",))})
    shutil.rmtree(tmp, ignore_errors=True)
    if errors:
        log(f"compare iter {k}{sfx} FAILED: " + "; ".join(errors[:5]))
        return {"sample": sfx or "-", "ok": False, "errors": errors}

    total = weighted_total(data)
    data["total"] = total
    data["weights"] = CFG["rubric_weights"]
    write_json(out_dir / "score.json", data)
    stu_guards = read_json(stu_dir / "guards.json", {})
    stu_stats = read_json(stu_dir / "stats.json", {})
    usage = stu_stats.get("usage", {})
    row = {"iter": k, "sample": sfx or "-", "total": total,
           **{key: data["dimensions"][key]["score"] for key in DIMENSIONS},
           "gaps_student_wrong": sum(1 for g in data["gaps"] if g["tag"] == "student_wrong"),
           "gaps_high": sum(1 for g in data["gaps"]
                            if g["tag"] == "student_wrong" and g["severity"] == "high"),
           "validate_ok": stu_guards.get("validate", {}).get("ok"),
           "leak_ok": stu_guards.get("leak", {}).get("ok"),
           "no_code_ok": stu_guards.get("no_code", {}).get("ok"),
           "hmos_coverage": stu_stats.get("hmos_coverage"),
           "subagents": stu_stats.get("subagents"),
           "input_tokens": usage.get("inputTokens"), "output_tokens": usage.get("outputTokens"),
           "duration_min": round((stu_stats.get("duration_ms") or 0) / 60000, 1),
           "model": stu_stats.get("model_reported")}
    csv_path = run_dir(run_id) / "scores.csv"
    rows = [r for r in read_csv(csv_path) if not (r["iter"] == str(k) and r["sample"] == row["sample"])]
    rows.append(row)
    rows.sort(key=lambda r: (int(r["iter"]), r["sample"]))
    write_csv(csv_path, rows)
    log(f"compare iter {k}{sfx}: total {total} "
        f"({', '.join(f'{key} {data['dimensions'][key]['score']}' for key in DIMENSIONS)})")
    return {"sample": sfx or "-", "ok": True, "total": total}


def cmd_compare(args) -> None:
    state = load_state(args.run)
    verify_frozen(args.run, state)
    k = args.iter
    samples = state["iters"].get(str(k), {}).get("samples", 1)
    with ThreadPoolExecutor(max_workers=samples) as pool:
        results = [f.result() for f in [pool.submit(run_compare_sample, args.run, state, k, s, samples)
                                        for s in range(1, samples + 1)]]
    state = load_state(args.run)
    it = state["iters"].setdefault(str(k), {})
    it["compare"] = results
    totals = [r["total"] for r in results if r.get("ok")]
    it["score"] = round(statistics.mean(totals), 1) if totals else None
    save_state(args.run, state)


# ---------------------------------------------------------------- synthesize

def cmd_synthesize(args) -> None:
    state = load_state(args.run)
    verify_frozen(args.run, state)
    k = args.iter
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
    prev = iter_dir(args.run, k - 1) / "playbook" / "playbook.md"
    if k > 0 and prev.exists():
        inputs["previous_playbook.md"] = prev
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
    ref_caps = list(read_json(oracle_dir(args.run) / "metrics.json", {})
                    .get("baseline_capabilities", {}).keys())
    retries = CFG.get("synth_fix_retries", 0)
    for attempt in range(retries + 1):
        report = guards.check_playbook(CFG, ws / "_outputs" / "playbook.md", oracle_spec(args.run),
                                       base_dir(args.run), ref_caps)
        if report["ok"] or not meta.get("session_id") or attempt == retries:
            break
        log(f"playbook rejected ({'; '.join(report['problems'])}); asking for a rewrite")
        spans = "\n".join(f"- {s}" for s in report.get("spans", [])[:10]) or "- none"
        meta = run_agent(model=sm, ws=ws, prompt=SYNTH_FIX_PROMPT.format(
            problems="\n".join(f"- {p}" for p in report["problems"]), spans=spans),
            out_dir=out_dir, label=f"fix{attempt + 1}", timeout_min=timeout_for(state, "synthesizer"),
            resume_session=meta["session_id"])
    write_json(out_dir / "overlap_report.json", report)
    for name in ("playbook.md", "changelog.md"):
        if (ws / "_outputs" / name).exists():
            (out_dir / name).write_bytes((ws / "_outputs" / name).read_bytes())
    if not report["ok"] and (out_dir / "playbook.md").exists():
        (out_dir / "playbook.md").rename(out_dir / "playbook.rejected.md")
    render_traj.render(out_dir / "trajectory.jsonl", ws, out_dir / "trajectory.md",
                       out_dir / "stats.json", CFG, CFG["hmos_dir"], out_dir / "transcripts" / "trajectory",
                       title=f"synthesizer iter {k}")
    write_json(out_dir / "guards.json", {"no_code": guards.no_code(ws, ("_outputs/",))})
    shutil.rmtree(tmp, ignore_errors=True)
    state = load_state(args.run)
    state["iters"].setdefault(str(k), {})["playbook"] = {
        "ok": report["ok"], "problems": report.get("problems", []), "from_sample": chosen["sample"],
        "lines": report.get("lines"), "copied_chars": report.get("copied_chars")}
    save_state(args.run, state)
    if report["ok"]:
        log(f"playbook for iteration {k + 1} written: {out_dir / 'playbook.md'} ({report['lines']} lines)")
    else:
        log("playbook REJECTED after retries: " + "; ".join(report["problems"]))


# ---------------------------------------------------------------- iterate / status / smoke

def cmd_iterate(args) -> None:
    state = load_state(args.run)
    verify_frozen(args.run, state)
    plateau = CFG.get("plateau", 2)
    last = args.start + (args.iters or CFG["iterations"]) - 1
    for k in range(args.start, last + 1):
        state = load_state(args.run)
        it = state["iters"].get(str(k), {})
        if not any(r.get("valid") for r in it.get("student", [])):
            cmd_student(argparse.Namespace(run=args.run, iter=k, samples=args.samples, dry_run=False))
            state = load_state(args.run)
            if not any(r.get("valid") for r in state["iters"][str(k)]["student"]):
                die(f"iteration {k}: no valid student run; inspect {iter_dir(args.run, k)}")
        if state["iters"][str(k)].get("score") is None:
            cmd_compare(argparse.Namespace(run=args.run, iter=k))
            state = load_state(args.run)
            if state["iters"][str(k)].get("score") is None:
                die(f"iteration {k}: comparison failed; inspect {iter_dir(args.run, k)}")
        scores = {int(j): v["score"] for j, v in state["iters"].items() if v.get("score") is not None}
        best_iter = max(scores, key=lambda j: (scores[j], -j))
        log(f"iteration {k}: score {scores[k]} (best {scores[best_iter]} at iteration {best_iter})")
        if k - best_iter >= plateau:
            log(f"no improvement for {plateau} iterations; stopping. Best playbook: "
                f"{iter_dir(args.run, best_iter - 1) / 'playbook' / 'playbook.md' if best_iter else 'none (iteration 0)'}")
            return
        if not state["iters"][str(k)].get("playbook", {}).get("ok"):
            cmd_synthesize(argparse.Namespace(run=args.run, iter=k))
            state = load_state(args.run)
            if not state["iters"][str(k)].get("playbook", {}).get("ok"):
                die(f"iteration {k}: no acceptable playbook; inspect {iter_dir(args.run, k) / 'playbook'}")
    log(f"finished iterations {args.start}..{last}")


def cmd_status(args) -> None:
    state = load_state(args.run)
    o = state["oracle"]
    print(f"run {args.run}{' (smoke)' if smoke(state) else ''}")
    print(f"  oracle: {o.get('status')}  validate={o.get('validate_ok')}  frozen={state.get('frozen')}"
          f"  session={o.get('session_id')}")
    if o.get("problems"):
        print(f"  oracle problems: {'; '.join(o['problems'])}")
    for k in sorted(state["iters"], key=int):
        it = state["iters"][k]
        st = ", ".join(f"{r['sample']}:{'valid' if r.get('valid') else 'INVALID'}"
                       for r in it.get("student", []))
        pb = it.get("playbook", {})
        print(f"  iter {int(k):02d}: student [{st}]  score={it.get('score')}  "
              f"playbook={'ok' if pb.get('ok') else ('rejected' if pb else '-')}")
    rows = read_csv(run_dir(args.run) / "scores.csv")
    if rows:
        print("\n  " + "  ".join(f"{c}" for c in ("iter", "sample", "total", *DIMENSIONS)))
        for r in rows:
            print("  " + "  ".join(str(r.get(c, "")) for c in ("iter", "sample", "total", *DIMENSIONS)))


def cmd_smoke(args) -> None:
    if not (run_dir(args.run) / "state.json").exists():
        cmd_prepare(argparse.Namespace(run=args.run, force=False, smoke=True))
    state = load_state(args.run)
    if not smoke(state):
        die(f"run '{args.run}' is not a smoke run")
    if state["oracle"].get("status") in ("pending", "failed"):
        cmd_oracle(argparse.Namespace(run=args.run, revise=None, revise_file=None))
    state = load_state(args.run)
    if not state.get("frozen"):
        cmd_freeze(argparse.Namespace(run=args.run, force=True))
    verify_frozen(args.run, load_state(args.run))
    if not load_state(args.run)["iters"].get("0", {}).get("student"):
        cmd_student(argparse.Namespace(run=args.run, iter=0, samples=1, dry_run=False))
    if load_state(args.run)["iters"]["0"].get("score") is None:
        cmd_compare(argparse.Namespace(run=args.run, iter=0))
    if not load_state(args.run)["iters"]["0"].get("playbook"):
        cmd_synthesize(argparse.Namespace(run=args.run, iter=0))

    state = load_state(args.run)
    checks = []
    rd = run_dir(args.run)
    for stage in ("oracle", "iter-00/student", "iter-00/compare", "iter-00/playbook"):
        meta = read_json(rd / stage / "trajectory.run.json", {})
        checks.append((f"{stage}: model reported '{meta.get('model_reported')}'", meta.get("model_ok")))
        checks.append((f"{stage}: run finished", meta.get("has_result") and not meta.get("is_error")))
        checks.append((f"{stage}: transcript copied", bool(meta.get("transcript_copy"))))
        checks.append((f"{stage}: trajectory.md rendered", (rd / stage / "trajectory.md").exists()))
    for stage in ("oracle", "iter-00/student"):
        g = read_json(rd / stage / "guards.json", {})
        checks.append((f"{stage}: only openspec/ written", g.get("no_code", {}).get("ok")))
        checks.append((f"{stage}: openspec validate", g.get("validate", {}).get("ok")))
        checks.append((f"{stage}: leak-free", g.get("leak", {}).get("ok")))
    checks.append(("oracle frozen and manifest verified", state.get("frozen")))
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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("prepare", help="create runs/<run>/ with inputs.lock.json and the base snapshot")
    p.add_argument("--run", required=True)
    p.add_argument("--force", action="store_true")
    p.add_argument("--smoke", action="store_true", help="use the small smoke task and smoke model")
    p.set_defaults(fn=cmd_prepare)

    p = sub.add_parser("oracle", help="run the oracle, or revise its spec with --revise")
    p.add_argument("--run", required=True)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--revise", help="reviewer feedback; resumes the oracle session")
    g.add_argument("--revise-file", help="file containing reviewer feedback")
    p.set_defaults(fn=cmd_oracle)

    p = sub.add_parser("freeze", help="hash the reviewed oracle spec and make it read-only")
    p.add_argument("--run", required=True)
    p.add_argument("--force", action="store_true", help="freeze even if validation fails")
    p.set_defaults(fn=cmd_freeze)

    p = sub.add_parser("student", help="run the student for one iteration")
    p.add_argument("--run", required=True)
    p.add_argument("--iter", type=int, required=True)
    p.add_argument("--samples", type=int, default=1)
    p.add_argument("--dry-run", action="store_true", help="print the prompt and exit")
    p.set_defaults(fn=cmd_student)

    p = sub.add_parser("compare", help="judge the student spec(s) of one iteration")
    p.add_argument("--run", required=True)
    p.add_argument("--iter", type=int, required=True)
    p.set_defaults(fn=cmd_compare)

    p = sub.add_parser("synthesize", help="write the playbook for the next iteration")
    p.add_argument("--run", required=True)
    p.add_argument("--iter", type=int, required=True)
    p.set_defaults(fn=cmd_synthesize)

    p = sub.add_parser("iterate", help="student -> compare -> synthesize for several iterations")
    p.add_argument("--run", required=True)
    p.add_argument("--iters", type=int, default=None, help="default: config.json iterations")
    p.add_argument("--start", type=int, default=0)
    p.add_argument("--samples", type=int, default=1)
    p.set_defaults(fn=cmd_iterate)

    p = sub.add_parser("status", help="show the state and score history of a run")
    p.add_argument("--run", required=True)
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("smoke", help="end-to-end plumbing test with the smoke task")
    p.add_argument("--run", required=True)
    p.set_defaults(fn=cmd_smoke)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
