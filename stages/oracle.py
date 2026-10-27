"""prepare, oracle and extract: the run, and its reference formed from several oracles.

`oracle` runs independent oracles. Each oracle's spec is repaired, in the same session, only
against checks code can make: `openspec validate --strict` and, once it validates, the values
AGENTS.md settles, read from two extraction passes. Then the reference is formed in code: the
decisions a majority of the oracles state, the HMOS names a majority cite, and the spec of the
oracle closest to that consensus (the medoid). No human review is involved.
"""

from __future__ import annotations

import shutil

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from lib import consensus as cons
from lib import decisions as dec
from lib import workspace
from lib.common import (ROOT, copy_tree, die, git, keep_attempt, load_state, log, make_readonly, make_writable,
                        read_json, remove_tree, run_dir, save_state, sha256_bytes, sha256_file, state_update,
                        timestamp, write_json, write_text_atomic)

from .core import (CFG, CONSENSUS_FILE, DECISIONS_FILE, base_dir, hmos_index, manifest_expected, model_for,
                   oracle_dir, oracle_runs, shared_idents, task_text, verify_frozen)
from .provenance import (check_inputs_unchanged, current_inputs, file_hashes, json_digest, reference_drift,
                         reference_inputs)
from .agents import VALIDATE_FAILS, post_spec_stage, spec_run, validate_failure
from .extraction import extract_playbook, extract_spec


REPAIR_PROMPT = """An automatic check of the OpenSpec you wrote in this workspace found the problems below.
Fix them in the spec. Keep every rule of the original task (write only under openspec/, no questions,
zh-CN prose), and finish only when `openspec validate --all --strict` passes.

Problems:

{problems}
"""
EXTRACTION_FAILED = "the extractor failed on the validated spec (`loop.py oracle` runs only the extraction again)"


def cmd_prepare(args) -> None:
    rd = run_dir(args.run)
    if (rd / "state.json").exists() and not args.force:
        die(f"run '{args.run}' already exists (use --force to re-prepare)")
    src = args.reference_from
    if src:
        src_state = load_state(src)
        verify_frozen(src, src_state)
        if not src_state.get("reference_decisions", {}).get("frozen"):
            die(f"run '{src}' has no frozen reference decisions; run `loop.py oracle --run {src}` first")
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
    od = oracle_dir(args.run)
    remove_tree(od)
    if src:
        sd = oracle_dir(src)
        copy_tree(sd / "spec", od / "spec")
        make_readonly(od / "spec")
        for name in ("MANIFEST.sha256", DECISIONS_FILE, CONSENSUS_FILE, "consensus.md", "guards.json", "metrics.json"):
            if (sd / name).exists():
                shutil.copy2(sd / name, od / name)
                if name in (DECISIONS_FILE, CONSENSUS_FILE):
                    make_readonly(od / name)
        state.update(frozen=True, frozen_at=src_state.get("frozen_at"),
                     reference_decisions={**src_state["reference_decisions"], "copied_from": src})
        state["oracle"] = {"status": "frozen", "reference_from": src,
                           **{k: src_state["oracle"][k] for k in ("validate_ok", "medoid") if k in src_state["oracle"]}}
        lock["reference_from"] = {"run": src, "manifest_sha256": sha256_file(od / "MANIFEST.sha256"),
                                  "decisions_sha256": sha256_file(od / DECISIONS_FILE),
                                  **({"accepted_drift": ref_drift} if ref_drift else {})}
    write_json(rd / "inputs.lock.json", lock)
    save_state(args.run, state)
    if src:
        verify_frozen(args.run, state)
    log(f"prepared run '{args.run}' at {rd} (base {sha[:12]}{', smoke' if args.smoke else ''}"
        f"{f', frozen reference and decisions from {src}' if src else ''})")


def oracle_keys(run_id: str, state: dict, text: str) -> tuple[str, str]:
    """(spec key, extraction key): what an oracle's spec, and its extraction, were made under. A
    spec made under another key is run again; only an extraction made under another key is only
    extracted again."""
    spec = json_digest({"prompt": sha256_bytes(text.encode("utf-8")),
                        "lock": sha256_file(run_dir(run_id) / "inputs.lock.json"), "model": model_for(state, "oracle")})
    extraction = json_digest({"inputs": file_hashes(reference_inputs(state)), "model": model_for(state, "extractor")})
    return spec, extraction


def oracle_problems(meta: dict, result: dict) -> list[str]:
    """Why an oracle run cannot be used. A failing `openspec validate` is not among them: the
    repair rounds handle it."""
    missing = [m for m in meta.get("incomplete") or [] if not m.startswith(VALIDATE_FAILS)]
    return [p for p, bad in (("the agent run failed", not meta.get("ok")),
                             ("leak", not result["leak"]["ok"]),
                             ("files were written outside openspec/", not result["no_code"]["ok"]),
                             ("deliverables missing: " + "; ".join(missing), bool(missing))) if bad]


def agreed_decisions(run_id: str, state: dict, od: Path, label: str, vocab: dict) -> dict | None:
    """Extract the oracle's spec twice in parallel and keep the values both passes agree on
    (decisions/pass-1, pass-2, agreement.json, agreed.json); None when a pass fails."""
    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.map(lambda p: extract_spec(run_id, state, od / "spec", od / "decisions" / f"pass-{p}",
                                               f"extract-oracle-{label}-p{p}", f"extract oracle {label} pass {p}"),
                        (1, 2))
    if a is None or b is None:
        return None
    agreed = cons.agreed_table(a, b, vocab)
    ag = dec.extraction_agreement(a, b, vocab)
    write_json(od / "decisions" / "agreement.json", ag)
    write_json(od / "decisions" / "agreed.json", agreed)
    log(f"oracle {label}: extraction passes agree on {ag['stated_agreement']:.1%} of the {ag['stated_items']} "
        f"stated keys; {len(ag['diffs'])} abstained")
    return agreed


def contradiction_line(c: dict) -> str:
    quote = f" The spec says: “{c['quotes'][0][:200]}”" if c["quotes"] else ""
    return (f"{c['label']}: the spec decides `{c['value']}` ({c['value_meaning']}), but AGENTS.md settles it as "
            f"`{c['agents_value']}` ({c['agents_meaning']}).{quote}")


def extract_again(run_id: str, state: dict, label: str, od: Path, old: dict, extraction_key: str,
                  vocab: dict) -> dict:
    """The spec stands; extract it again under the current extraction inputs (no repair: its
    contradictions with AGENTS.md, if any, are overridden by the consensus)."""
    log(f"oracle {label}: extracting its spec again")
    agreed = agreed_decisions(run_id, state, od, label, vocab)
    record = {**old, "valid": agreed is not None, "problems": [] if agreed else [EXTRACTION_FAILED],
              "needs_extraction": agreed is None, "extraction_key": extraction_key,
              "contradictions": [c["id"] for c in cons.agents_contradictions(agreed, vocab)] if agreed else [],
              "finished_at": timestamp()}
    write_json(od / "oracle.json", record)
    return record


def run_oracle_sample(run_id: str, state: dict, label: str, od: Path, text: str, keys: tuple[str, str],
                      vocab: dict) -> dict:
    """One oracle in a fresh workspace, then repair rounds in its session (at most
    `oracle_repair_rounds`): first until the spec validates, then while two extractions show it
    contradicting AGENTS.md. A repair that breaks a validated spec, with no round left to fix it,
    is undone. Retried from scratch while unusable (`oracle_retries`), except when only the
    extraction failed; earlier runs are kept as o<i>.attemptN."""
    spec_key, extraction_key = keys
    old = read_json(od / "oracle.json")
    if old and old.get("spec_key") == spec_key and (old["valid"] or old.get("needs_extraction")):
        if old["valid"] and old.get("extraction_key") == extraction_key:
            log(f"oracle {label}: reusing the valid run in {od}")
            return old
        return extract_again(run_id, state, label, od, old, extraction_key, vocab)
    snapshot = od.parent / f".{od.name}.validated"
    for attempt in range(CFG["oracle_retries"] + 1):
        if od.exists() and any(od.iterdir()):
            keep_attempt(od)
        ws = workspace.build(CFG, run_id, f"oracle-{label}")
        labels, session, todo, needs_extraction = [], None, [], False
        remove_tree(snapshot)
        while True:
            labels.append(f"repair{len(labels)}" if labels else "trajectory")
            prompt_text = REPAIR_PROMPT.format(problems="\n".join(f"- {p}" for p in todo)) if todo else text
            meta = spec_run(state, "oracle", ws, prompt_text, od, labels[-1], resume_session=session)
            session = session or meta.get("session_id")
            result = post_spec_stage(run_id, ws, od, labels, f"oracle {label}")
            problems, contradictions = oracle_problems(meta, result), []
            if problems:
                break
            if result["validate"]["ok"]:
                agreed = agreed_decisions(run_id, state, od, label, vocab)
                if agreed is None:
                    problems, needs_extraction = [EXTRACTION_FAILED], True
                    break
                contradictions = cons.agents_contradictions(agreed, vocab)
                todo = [contradiction_line(c) for c in contradictions]
                if todo:
                    copy_tree(od / "spec", snapshot)
            else:
                todo = [validate_failure(result["validate"])]
            if not todo:
                break
            if not session or len(labels) > CFG["oracle_repair_rounds"]:
                if not result["validate"]["ok"] and snapshot.exists():
                    log(f"oracle {label}: the repair broke the validated spec; restoring it")
                    copy_tree(snapshot / "openspec", ws / "openspec")
                    result = post_spec_stage(run_id, ws, od, labels, f"oracle {label}")
                    contradictions = cons.agents_contradictions(read_json(od / "decisions" / "agreed.json"), vocab)
                if not result["validate"]["ok"]:
                    problems = [f"{VALIDATE_FAILS} after {len(labels) - 1} repair round(s)"
                                + ("" if session else " (no session to repair)")]
                break
            log(f"oracle {label}: {len(todo)} problem(s) for code checks; repair round {len(labels)}")
        remove_tree(snapshot)
        record = {"oracle": label, "valid": not problems, "problems": problems, "spec_key": spec_key,
                  "extraction_key": extraction_key, "needs_extraction": needs_extraction, "repairs": len(labels) - 1,
                  "contradictions": [c["id"] for c in contradictions],
                  "attempts": 1 + len(list(od.parent.glob(f"{od.name}.attempt*"))), "finished_at": timestamp()}
        write_json(od / "oracle.json", record)
        if not problems or needs_extraction:
            log(f"oracle {label}: " + ("; ".join(problems) if problems else f"valid after {record['repairs']} repair "
                                       f"round(s)") + (f"; contradicts AGENTS.md on {', '.join(record['contradictions'])}"
                                                       f" (the consensus takes AGENTS.md's values)" if contradictions else ""))
            break
        log(f"oracle {label}: unusable ({'; '.join(problems)})"
            + (f"; retrying from scratch ({attempt + 1}/{CFG['oracle_retries']})" if attempt < CFG["oracle_retries"]
               else ""))
    return record


def cmd_oracle(args) -> None:
    """Run the oracles (reusing valid ones made under the same inputs), then form and freeze the
    reference; every oracle must be usable."""
    state = load_state(args.run)
    if state.get("frozen"):
        die("the reference is frozen; it cannot be regenerated")
    check_inputs_unchanged(args.run, args.allow_drift)
    runs, text, vocab = oracle_runs(args.run, state), task_text(state), dec.load_vocab()
    keys = oracle_keys(args.run, state, text)
    log(f"{len(runs)} independent oracles")
    with ThreadPoolExecutor(max_workers=len(runs)) as pool:
        records = list(pool.map(lambda r: run_oracle_sample(args.run, state, *r, text, keys, vocab), runs))
    invalid = [r for r in records if not r["valid"]]
    if invalid:
        with state_update(args.run) as st:
            st["oracle"]["status"] = "failed"
        die("the reference needs every oracle, and these are still unusable after their retries: " +
            "; ".join(f"{r['oracle']}: {', '.join(r['problems'])}" for r in invalid) +
            f". Fix the cause and run `loop.py oracle --run {args.run}` again: valid oracles are reused, and an "
            f"oracle whose extraction failed is only extracted again.")
    form_reference(args.run, state, runs, vocab)


def form_reference(run_id: str, state: dict, runs: list[tuple[str, Path]], vocab: dict) -> None:
    """The consensus decisions (decisions.json), coverage names and votes (consensus.json,
    consensus.md), and the medoid's spec, guards and metrics; hashed in MANIFEST.sha256 and
    read-only, then the run is marked frozen."""
    labels, dirs = [lab for lab, _d in runs], [d for _lab, d in runs]
    index, shared = hmos_index(run_id), shared_idents(run_id, state)
    tables = [read_json(d / "decisions" / "agreed.json") for d in dirs]
    name_sets = [dec.cited_names(d / "spec", CFG, index, shared) for d in dirs]
    cv = cons.consensus_values(tables, vocab)
    names = cons.consensus_names(name_sets)
    scores = [(cons.agreement(t, cv["values"], vocab), cons.jaccard(s, names)) for t, s in zip(tables, name_sets)]
    m = cons.pick_medoid(scores)
    table = cons.consensus_table(tables, cv["values"], m, labels, vocab)

    od = oracle_dir(run_id)
    copy_tree(dirs[m] / "spec", od / "spec")
    for name in ("guards.json", "metrics.json"):
        shutil.copy2(dirs[m] / name, od / name)
    report = {"oracles": labels, "majority": cons.majority(len(runs)), "medoid": labels[m],
              "stated": dec.stated_count(table), "contested": cv["contested"], "overrides": cv["overrides"],
              "medoid_dissent": cons.dissent(tables[m], cv["values"], vocab), "votes": cv["votes"],
              "names": sorted(names),
              "per_oracle": {lab: {"agreement": a, "names_jaccard": j} for lab, (a, j) in zip(labels, scores)},
              "formed_at": timestamp()}
    for name, data in ((DECISIONS_FILE, table), (CONSENSUS_FILE, report)):
        make_writable(od / name)
        write_json(od / name, data)
        make_readonly(od / name)
    write_text_atomic(od / "consensus.md", cons.render_md(report))
    make_readonly(od / "spec")
    write_text_atomic(od / "MANIFEST.sha256", manifest_expected(run_id, {"reference_decisions": {"frozen": True}}))
    with state_update(run_id) as st:
        st.update(frozen=True, frozen_at=timestamp())
        st["oracle"] = {"status": "frozen", "medoid": labels[m]}
        st["reference_decisions"] = {"frozen": True, "frozen_at": st["frozen_at"],
                                     "sha256": sha256_file(od / DECISIONS_FILE), "stated": report["stated"],
                                     "extracted_under": file_hashes(reference_inputs(st))}
    log(f"reference frozen from {len(runs)} oracles: spec of {labels[m]} (closest to the consensus; it differs on "
        f"{len(report['medoid_dissent'])} decisions), {report['stated']} decisions with a majority, "
        f"{len(cv['contested'])} without (not scored), {len(cv['overrides'])} set to AGENTS.md's value, "
        f"{len(names)} coverage names; {od / 'consensus.md'}")


def cmd_extract(args) -> None:
    """Extract a decision table from a spec (a run-relative directory holding spec/) or a playbook
    (a run-relative .md file), in N parallel passes. An offline check: it touches neither
    state.json nor the reference."""
    if not args.out and Path(args.target).parts[:1] == ("oracle",):
        die("the oracle directories hold the reference's own extractions; pass --out to write elsewhere")
    state = load_state(args.run)
    rd = run_dir(args.run)
    target = rd / args.target
    is_playbook = target.suffix == ".md"
    if is_playbook and not target.exists():
        die(f"no playbook at {target}")
    if not is_playbook and not (target / "spec" / "openspec").is_dir():
        die(f"no spec at {target / 'spec' / 'openspec'}")
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
    if len(ok) >= 2:
        ag = dec.extraction_agreement(ok[0], ok[1], dec.load_vocab())
        write_json(out_root / "agreement.json", ag)
        log(f"passes agree on {ag['agreement']:.1%} of {ag['items']} keys "
            f"({ag['stated_agreement']:.1%} of the {ag['stated_items']} keys at least one pass states)")
        for d in ag["diffs"]:
            log(f"  differs: {d['id']}: {d['a']} vs {d['b']}")
