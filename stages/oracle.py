"""prepare, oracle, extract and freeze: the run, its reference spec and the reference decisions."""

from __future__ import annotations

import json
import shutil

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from lib import decisions as dec
from lib import guards, spec_metrics, workspace
from lib.common import (ROOT, copy_tree, die, git, load_state, log, make_readonly, make_writable, read_json,
                        remove_tree, run_dir, save_state, sha256_bytes, sha256_file, state_update, timestamp,
                        write_json, write_text_atomic)

from .core import (CFG, DECISIONS_FILE, base_dir, hmos_index, manifest_expected, manifest_text, oracle_dir,
                   oracle_spec, task_text, verify_frozen)
from .provenance import changed_files, current_inputs, file_hashes, reference_drift, reference_inputs
from .agents import post_spec_stage, spec_run
from .extraction import extract_playbook, extract_spec


REVISE_PROMPT = """A human reviewer read the OpenSpec you wrote in this workspace and asks for the changes below.
The files under openspec/ may also contain edits the reviewer made directly; keep those.
Apply the feedback, keep every rule of the original task (write only under openspec/, no questions,
zh-CN prose), and finish only when `openspec validate --all --strict` passes.

Reviewer feedback:

{feedback}
"""


def cmd_prepare(args) -> None:
    rd = run_dir(args.run)
    if (rd / "state.json").exists() and not args.force:
        die(f"run '{args.run}' already exists (use --force to re-prepare)")
    src = args.reference_from
    if src:
        src_state = load_state(src)
        verify_frozen(src, src_state)
        if not src_state.get("reference_decisions", {}).get("frozen"):
            die(f"run '{src}' has no frozen reference decisions; freeze them first")
        src_sha = read_json(run_dir(src) / "inputs.lock.json", {}).get("base_sha")
        if src_sha != CFG["base_sha"]:
            die(f"run '{src}' was prepared at base {src_sha}, config.json has {CFG['base_sha']}; "
                f"its reference does not apply to this base")
        ref_drift = reference_drift(src, src_state)
        if ref_drift:
            msg = (f"the reference decisions of run '{src}' were extracted under other inputs than this run "
                   f"scores with: {'; '.join(ref_drift)}")
            if not args.allow_drift:
                die(f"{msg}. Prepare a new oracle run, or pass --allow-drift to reuse them anyway")
            log(f"warning: {msg} (--allow-drift)")
    rd.mkdir(parents=True, exist_ok=True)
    remove_tree(base_dir(args.run))
    workspace.extract(CFG, base_dir(args.run))
    repo, sha = CFG["repo"], CFG["base_sha"]

    cur = current_inputs(bool(args.smoke))
    lock = {
        "created": timestamp(),
        "base_sha": sha,
        "files": {p: sha256_bytes(git(repo, "show", f"{sha}:{p}"))
                  for p in ("AGENTS.md", "openspec/config.yaml")},
        "hmos_tree": git(repo, "rev-parse", f"{sha}:{CFG['hmos_dir']}").decode().strip(),
        "skills": cur["skills"],
        "prompts": cur["prompts"],
        "config": sha256_file(ROOT / "config.json"),
        "config_fingerprint": cur["config"],
        "models": cur["models"],
        "agent_cli": cur["agent_cli"],
        "openspec_cli": cur["openspec_cli"],
        "smoke": bool(args.smoke),
    }
    if (rd / "hmos_index.json").exists():
        (rd / "hmos_index.json").unlink()
    hmos_index(args.run)
    state = {"run": args.run, "smoke": bool(args.smoke), "naming": "sN",
             "oracle": {"status": "pending"}, "frozen": False, "iters": {}}
    if src:
        od, sd = oracle_dir(args.run), oracle_dir(src)
        remove_tree(od)
        copy_tree(sd / "spec", od / "spec")
        make_readonly(od / "spec")
        for name in ("MANIFEST.sha256", DECISIONS_FILE, "guards.json", "metrics.json"):
            if (sd / name).exists():
                shutil.copy2(sd / name, od / name)
        make_readonly(od / DECISIONS_FILE)
        src_state = load_state(src)
        state.update(frozen=True, frozen_at=src_state.get("frozen_at"),
                     reference_decisions={**src_state["reference_decisions"], "copied_from": src})
        state["oracle"] = {"status": "frozen", "reference_from": src,
                           "validate_ok": src_state["oracle"].get("validate_ok")}
        lock["reference_from"] = {"run": src, "manifest_sha256": sha256_file(od / "MANIFEST.sha256"),
                                  "decisions_sha256": sha256_file(od / DECISIONS_FILE),
                                  **({"accepted_drift": ref_drift} if ref_drift else {})}
    write_json(rd / "inputs.lock.json", lock)
    save_state(args.run, state)
    if src:
        verify_frozen(args.run, state)
    log(f"prepared run '{args.run}' at {rd} (base {sha[:12]}{', smoke' if args.smoke else ''}"
        f"{f', frozen reference and decisions from {src}' if src else ''})")


def cmd_oracle(args) -> None:
    state = load_state(args.run)
    if state.get("frozen"):
        die("the oracle spec is frozen; it cannot be regenerated or revised")
    od = oracle_dir(args.run)
    ostate = state["oracle"]
    feedback = args.revise
    if args.revise_file:
        feedback = Path(args.revise_file).read_text(encoding="utf-8")

    if feedback is None:
        ws = workspace.build(CFG, args.run, "oracle")
        labels = ["trajectory"]
        meta = spec_run(state, "oracle", ws, task_text(state), od, "trajectory")
    else:
        if ostate.get("status") in (None, "pending") or not ostate.get("session_id"):
            die("there is no oracle session to revise; run `loop.py oracle` first")
        ws = Path(ostate["workspace"])
        copy = oracle_spec(args.run) / "openspec"
        if copy.exists() and manifest_text(copy) != manifest_text(ws / "openspec"):
            log("syncing reviewer edits from runs/.../oracle/spec into the oracle workspace")
            copy_tree(copy, ws / "openspec")
        labels = ostate.get("labels", ["trajectory"])
        label = f"revise{sum(1 for x in labels if x.startswith('revise')) + 1}"
        labels = [*labels, label]
        meta = spec_run(state, "oracle", ws, REVISE_PROMPT.format(feedback=feedback.strip()), od,
                        label, resume_session=ostate["session_id"])

    result = post_spec_stage(args.run, ws, od, labels, "oracle")
    fatal = []
    if not meta["ok"]:
        fatal.append("the agent run did not finish cleanly (see the .run.json)")
    if meta["incomplete"]:
        fatal.append("deliverables missing after nudges: " + "; ".join(meta["incomplete"]))
    if not result["no_code"]["ok"]:
        fatal.append("files were written outside openspec/")
    if not result["leak"]["ok"]:
        fatal.append("the trajectory touched forbidden paths")
    with state_update(args.run) as state:
        state["oracle"] = {
            "status": "failed" if fatal else "awaiting-review",
            "problems": fatal,
            "session_id": meta.get("session_id") or ostate.get("session_id"),
            "workspace": str(ws),
            "labels": labels,
            "validate_ok": result["validate"]["ok"],
        }
    if fatal:
        log("oracle run FAILED: " + "; ".join(fatal))
    else:
        log(f"oracle spec ready for review: {oracle_spec(args.run) / 'openspec'}")
        if not result["validate"]["ok"]:
            log("note: `openspec validate --all --strict` fails; see oracle/guards.json")
        log("next: edit the spec directly and/or `loop.py oracle --revise ...`, then `loop.py freeze`")


def freeze_reference_decisions(run_id: str) -> None:
    """Freeze oracle/decisions.proposed.json (as reviewed by the human) into oracle/decisions.json."""
    proposed = oracle_dir(run_id) / "decisions.proposed.json"
    if not proposed.exists():
        log(f"the reference decisions are not extracted yet: run `loop.py extract --run {run_id} --target "
            f"oracle`, review oracle/decisions.review.md, then `loop.py freeze --run {run_id}` again "
            f"(compare needs them)")
        return
    vocab = dec.load_vocab()
    clean, report = dec.validate_extraction(dec.to_raw(read_json(proposed)), vocab,
                                            dec.spec_corpus(oracle_spec(run_id), CFG), hmos_index(run_id),
                                            base_dir(run_id), CFG["hmos_dir"])
    if report["errors"]:
        die("oracle/decisions.proposed.json does not validate:\n" +
            "\n".join(f"- {e}" for e in report["errors"]))
    under = read_json(oracle_dir(run_id) / "decisions.proposed.provenance.json", {})
    changed = changed_files(under)
    if changed:
        log(f"warning: {', '.join(changed)} changed since the reference decisions were extracted")
    dst = oracle_dir(run_id) / DECISIONS_FILE
    if dst.exists():
        make_writable(dst)
    write_json(dst, clean)
    make_readonly(dst)
    with state_update(run_id) as state:
        state["reference_decisions"] = {
            "frozen": True, "frozen_at": timestamp(), "sha256": sha256_file(dst),
            "stated": sum(1 for k in dec.KINDS for e in clean[k].values() if e.get("value")),
            "extracted_under": under}
    write_text_atomic(oracle_dir(run_id) / "MANIFEST.sha256", manifest_expected(run_id, state))
    log(f"reference decisions frozen ({state['reference_decisions']['stated']} stated): {dst}")


def cmd_freeze(args) -> None:
    state = load_state(args.run)
    if state.get("frozen"):
        verify_frozen(args.run, state)
        if state.get("reference_decisions", {}).get("frozen"):
            log("already frozen (spec and reference decisions)")
        else:
            freeze_reference_decisions(args.run)
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
    write_text_atomic(oracle_dir(args.run) / "MANIFEST.sha256", manifest_text(spec_root))
    make_readonly(spec_root)
    with state_update(args.run) as state:
        state["frozen"] = True
        state["frozen_at"] = timestamp()
        state["oracle"]["status"] = "frozen"
    log(f"oracle spec frozen ({sum(1 for p in spec_root.rglob('*') if p.is_file())} files); "
        f"manifest at {oracle_dir(args.run) / 'MANIFEST.sha256'}")
    freeze_reference_decisions(args.run)


def cmd_extract(args) -> None:
    """Extract a decision table from a spec (a run-relative directory holding spec/) or a playbook
    (a run-relative .md file), in N parallel passes. For --target oracle this proposes the
    reference decisions for human review."""
    state = load_state(args.run)
    rd = run_dir(args.run)
    target = rd / args.target
    is_playbook = target.suffix == ".md"
    if is_playbook and not target.exists():
        die(f"no playbook at {target}")
    if not is_playbook and not (target / "spec" / "openspec").is_dir():
        die(f"no spec at {target / 'spec' / 'openspec'}")
    if args.target == "oracle" and state.get("reference_decisions", {}).get("frozen"):
        log("note: the reference decisions are already frozen; this only writes a new proposal")
    out_root = rd / args.out if args.out else (target.parent / "decisions" if is_playbook
                                               else target / "decisions")
    slug = args.target.strip("/").replace("/", "-").removesuffix(".md")

    def one(p: int):
        out, stage, title = out_root / f"pass-{p}", f"extract-{slug}-p{p}", f"extract {args.target} pass {p}"
        if is_playbook:
            return extract_playbook(args.run, state, target, out, stage, title)
        return extract_spec(args.run, state, target / "spec", out, stage, title)

    passes = max(1, args.passes)
    with ThreadPoolExecutor(max_workers=passes) as pool:
        tables = list(pool.map(one, range(1, passes + 1)))
    ok = [t for t in tables if t is not None]
    if not ok:
        die("every extraction pass failed")
    vocab = dec.load_vocab()
    ag = None
    if len(ok) >= 2:
        ag = dec.extraction_agreement(ok[0], ok[1], vocab)
        write_json(out_root / "agreement.json", ag)
        log(f"passes agree on {ag['agreement']:.1%} of {ag['items']} keys "
            f"({ag['stated_agreement']:.1%} of the {ag['stated_items']} keys at least one pass states)")
        for d in ag["diffs"]:
            log(f"  differs: {d['id']}: {d['a']} vs {d['b']}")
    if args.target == "oracle":
        write_json(oracle_dir(args.run) / "decisions.proposed.json", ok[0])
        write_json(oracle_dir(args.run) / "decisions.proposed.provenance.json", file_hashes(reference_inputs(state)))
        mod = dec.module_table(oracle_spec(args.run), hmos_index(args.run), CFG)
        (oracle_dir(args.run) / "decisions.review.md").write_text(
            dec.render_review(ok[0], mod, vocab, ag, ok[1] if len(ok) >= 2 else None), encoding="utf-8")
        log(f"proposed reference decisions: {oracle_dir(args.run) / 'decisions.proposed.json'}; review "
            f"{oracle_dir(args.run) / 'decisions.review.md'}, then `loop.py freeze --run {args.run}`")
