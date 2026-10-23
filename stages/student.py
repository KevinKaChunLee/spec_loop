"""Student runs: prompts, attempts and validity."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from lib import workspace
from lib.common import die, iter_dir, load_state, log, read_json, sha256_bytes, state_update, timestamp, write_json

from .core import (CFG, iteration_samples, key_label, sample_label, student_problems, student_valid, task_text,
                   verify_frozen)
from .provenance import check_inputs_unchanged
from .agents import post_spec_stage, spec_run


def playbook_prompt(state: dict, playbook: str | None) -> str:
    text = task_text(state)
    if playbook is None:
        return text
    return (text.rstrip() + "\n\n---\n\n# Playbook\n\n"
            "The playbook below comes from earlier attempts at this same task. Follow it.\n\n" +
            playbook.strip() + "\n")


def student_prompt(state: dict, run_id: str, k: int) -> str:
    if k == 0:
        return playbook_prompt(state, None)
    pb = iter_dir(run_id, k - 1) / "playbook" / "playbook.md"
    if not pb.exists():
        die(f"iteration {k} needs the playbook from iteration {k - 1}: {pb} is missing")
    return playbook_prompt(state, pb.read_text(encoding="utf-8"))


def keep_attempt(out_dir: Path) -> None:
    """Move a superseded student run aside as <out_dir>.attemptN (not read as a sample)."""
    n = 1
    while out_dir.with_name(f"{out_dir.name}.attempt{n}").exists():
        n += 1
    out_dir.rename(out_dir.with_name(f"{out_dir.name}.attempt{n}"))


def run_student(run_id: str, state: dict, out_dir: Path, stage: str, text: str, title: str,
                label: str) -> dict:
    """One student run in a fresh workspace, retried from scratch while it is invalid. Earlier
    runs (of this call or of an earlier one) are kept as <out_dir>.attemptN; `attempts` in
    provenance.json counts this run and the invalid ones before it, so a prompt that makes students
    fail more often shows up."""
    retries = CFG.get("student_retries", 0)
    if out_dir.exists() and any(out_dir.iterdir()):
        keep_attempt(out_dir)
    for attempt in range(retries + 1):
        ws = workspace.build(CFG, run_id, stage)
        meta = spec_run(state, "student", ws, text, out_dir, "trajectory")
        result = post_spec_stage(run_id, ws, out_dir, ["trajectory"], title)
        problems = student_problems(meta, result)
        prov = {"prompt_sha256": sha256_bytes(text.encode("utf-8")), "valid": not problems,
                "problems": problems, "finished_at": timestamp()}
        write_json(out_dir / "provenance.json", prov)
        if not problems or attempt == retries:
            break
        log(f"{title}: invalid run ({'; '.join(problems)}); retrying ({attempt + 1}/{retries})")
        keep_attempt(out_dir)
    earlier = sorted(out_dir.parent.glob(f"{out_dir.name}.attempt*"),
                     key=lambda d: int(d.name.rsplit("attempt", 1)[1]))
    prov["earlier_attempts"] = [{"dir": d.name, "valid": student_valid(d),
                                 "problems": read_json(d / "provenance.json", {}).get("problems")} for d in earlier]
    prov["attempts"] = 1 + sum(1 for e in prov["earlier_attempts"] if not e["valid"])
    write_json(out_dir / "provenance.json", prov)
    return {"sample": label or "-", "valid": not problems, "agent_ok": meta["ok"],
            "leak_ok": result["leak"]["ok"], "no_code_ok": result["no_code"]["ok"],
            "validate_ok": result["validate"]["ok"], "nudges": meta["nudges"],
            "incomplete": meta["incomplete"], "session_id": meta.get("session_id"),
            "workspace": str(ws), "attempts": prov["attempts"]}


def prompt_differs(stu_dir: Path, text: str) -> bool:
    """The run's provenance.json records another prompt than `text` (runs without one predate the
    record and are not checked)."""
    return read_json(stu_dir / "provenance.json", {}).get("prompt_sha256") not in (
        None, sha256_bytes(text.encode("utf-8")))


def stale_students(run_id: str, k: int, text: str) -> list[str]:
    """Samples of iteration k that were run with another prompt than `text`."""
    return [label for label, s, _c in iteration_samples(run_id, k) if prompt_differs(s, text)]


def run_student_sample(run_id: str, state: dict, k: int, sample: int, samples: int,
                       text: str) -> dict:
    sfx = sample_label(state, sample, samples)
    return run_student(run_id, state, iter_dir(run_id, k) / f"student{sfx}", f"iter-{k:02d}-student{sfx}",
                       text, f"student iter {k}{sfx}", sfx)


def cmd_student(args) -> None:
    state = load_state(args.run)
    k = args.iter
    if k > 0 or state.get("frozen"):
        verify_frozen(args.run, state)
    check_inputs_unchanged(args.run, args.allow_drift)
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
    with state_update(args.run) as state:
        it = state["iters"].setdefault(str(k), {})
        it["samples"] = samples
        it["student"] = results
    for r in results:
        log(f"student iter {k} sample {r['sample']}: valid={r['valid']} validate={r['validate_ok']} "
            f"only-openspec={r['no_code_ok']}")


def student_attempts(state: dict, k: int, label: str, stu_dir: Path) -> int | None:
    """From the run's provenance.json, or for older runs from state.json; `label` is a sample's
    label or its state.json name."""
    prov = read_json(stu_dir / "provenance.json", {})
    if prov.get("attempts"):
        return prov["attempts"]
    return next((r.get("attempts") for r in state["iters"].get(str(k), {}).get("student", [])
                 if key_label(r.get("sample", "-")) == key_label(label)), None)
