"""Extract a decision table from a spec or a playbook."""

from __future__ import annotations

import copy

from pathlib import Path

from lib import decisions as dec
from lib import workspace
from lib.common import log, prompt, write_json

from .core import CFG, base_dir, hmos_index, task_text
from .agents import run_checked_agent


def extract_decisions(run_id: str, state: dict, stage: str, out_dir: Path, inputs: dict[str, Path],
                      prompt_name: str, corpus: dict[str, str], require_all: bool, title: str) -> dict | None:
    """Run the extractor; write decisions.raw.json, decisions.json (validated) and validation.json."""
    index, vocab = hmos_index(run_id), dec.load_vocab()
    out_dir.mkdir(parents=True, exist_ok=True)
    ws = workspace.build(CFG, run_id, stage, {**inputs, "decision_vocab.json": dec.VOCAB_PATH})
    report: dict = {}

    def check(raw):
        write_json(out_dir / "decisions.raw.json", raw)
        clean, rep = dec.validate_extraction(copy.deepcopy(raw), vocab, corpus, index, base_dir(run_id),
                                             CFG["hmos_dir"], require_all)
        report.clear()
        report.update(rep)
        return clean, rep["errors"]
    table, errors = run_checked_agent(state, "extractor", run_id, ws,
                                      prompt(prompt_name, change_name=CFG["change_name"]), out_dir,
                                      "decisions.json", check, CFG.get("extract_fix_retries", 0), title, ())
    if table is None:
        write_json(out_dir / "validation.json", {"errors": errors})
        log(f"{title} FAILED: " + "; ".join(errors[:5]))
        return None
    write_json(out_dir / "decisions.json", table)
    write_json(out_dir / "validation.json", report)
    stated = dec.stated_count(table)
    log(f"{title}: {stated} decisions stated, {len(report.get('dropped', []))} dropped as invalid, "
        f"{len(report.get('warnings', []))} warnings")
    return table


def extract_spec(run_id: str, state: dict, spec_root: Path, out_dir: Path, stage: str,
                 title: str) -> dict | None:
    return extract_decisions(run_id, state, stage, out_dir, {"spec": spec_root}, "extract.md",
                             dec.spec_corpus(spec_root, CFG), True, title)


def extract_playbook(run_id: str, state: dict, playbook: Path, out_dir: Path, stage: str,
                     title: str) -> dict | None:
    text = playbook.read_text(encoding="utf-8", errors="replace")
    out_dir.mkdir(parents=True, exist_ok=True)
    task = out_dir / "_task.md"
    task.write_text(task_text(state), encoding="utf-8")
    table = extract_decisions(run_id, state, stage, out_dir, {"playbook.md": playbook, "task.md": task},
                              "extract_playbook.md", {"playbook.md": text}, False, title)
    task.unlink(missing_ok=True)
    return table
