"""Tests of the oracle stage's control flow (stages/oracle.py) with the agent runs, guards and
extractions faked: repair order and limits, undoing a repair that breaks a validated spec,
extraction-only retries, reuse, and forming and freezing the reference.

    cd spec_loop && python3 -m unittest discover -s tests -t .
"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import lib.common as common
from stages import core
from stages import oracle as orc
from tests.test_consensus import VOCAB, table

RUN = "t"
KEYS = ("spec-1", "extraction-1")


class FakeAgents:
    """Each oracle turn writes the next scripted content to openspec/state.txt: "valid..." passes
    validation, "...contradiction" makes the extraction contradict AGENTS.md (dsda keep)."""

    def __init__(self, script: list[str], session: str | None = "sess"):
        self.script, self.session = list(script), session
        self.prompts: list[str] = []
        self.extractions = 0
        self.extract_fails = False

    def spec_run(self, state, role, ws, prompt_text, od, label, resume_session=None):
        self.prompts.append(prompt_text)
        (ws / "openspec").mkdir(parents=True, exist_ok=True)
        (ws / "openspec" / "state.txt").write_text(self.script.pop(0), encoding="utf-8")
        return {"ok": True, "incomplete": [], "session_id": self.session}

    def post_spec_stage(self, run_id, ws, od, labels, title):
        common.copy_tree(ws / "openspec", od / "spec" / "openspec")
        ok = (ws / "openspec" / "state.txt").read_text(encoding="utf-8").startswith("valid")
        return {"validate": {"ok": ok, "failed": [] if ok else [{"id": "cap", "issues": ["broken"]}]},
                "no_code": {"ok": True}, "leak": {"ok": True}}

    def extract_spec(self, run_id, state, spec_root, out_dir, stage, title):
        self.extractions += 1
        if self.extract_fails:
            return None
        text = (spec_root / "openspec" / "state.txt").read_text(encoding="utf-8")
        return table(dsda="keep" if "contradiction" in text else "remove")


class RunTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for p in (mock.patch.object(common, "RUNS", self.root / "runs"), mock.patch.object(orc, "log"),
                  mock.patch.dict(orc.CFG, oracle_retries=1, oracle_repair_rounds=2)):
            p.start()
            self.addCleanup(p.stop)
        self.state = {"run": RUN, "smoke": False, "oracle": {"status": "pending"}, "frozen": False, "iters": {}}
        common.save_state(RUN, self.state)
        self.od = core.oracle_dir(RUN) / "o1"

    def fake(self, agents: FakeAgents) -> None:
        def build(cfg, run_id, stage):
            ws = self.root / "ws" / stage
            common.remove_tree(ws)
            ws.mkdir(parents=True)
            return ws
        for p in (mock.patch.object(orc.workspace, "build", side_effect=build),
                  mock.patch.object(orc, "spec_run", agents.spec_run),
                  mock.patch.object(orc, "post_spec_stage", agents.post_spec_stage),
                  mock.patch.object(orc, "extract_spec", agents.extract_spec)):
            p.start()
            self.addCleanup(p.stop)

    def run_oracle(self, keys=KEYS) -> dict:
        return orc.run_oracle_sample(RUN, self.state, "o1", self.od, "TASK", keys, VOCAB)

    def spec_text(self) -> str:
        return (self.od / "spec" / "openspec" / "state.txt").read_text(encoding="utf-8")


class RepairTest(RunTest):
    def test_a_valid_spec_is_extracted_once_and_accepted(self):
        agents = FakeAgents(["valid"])
        self.fake(agents)
        r = self.run_oracle()
        self.assertEqual((r["valid"], r["repairs"], r["contradictions"], agents.extractions), (True, 0, [], 2))
        self.assertEqual(agents.prompts, ["TASK"])

    def test_validation_is_repaired_before_any_extraction(self):
        agents = FakeAgents(["broken", "valid"])
        self.fake(agents)
        r = self.run_oracle()
        self.assertEqual((r["valid"], r["repairs"], agents.extractions), (True, 1, 2))
        self.assertIn("openspec validate", agents.prompts[1])

    def test_contradictions_are_repaired(self):
        agents = FakeAgents(["valid-contradiction", "valid"])
        self.fake(agents)
        r = self.run_oracle()
        self.assertEqual((r["valid"], r["repairs"], r["contradictions"]), (True, 1, []))
        self.assertIn("AGENTS.md settles it as `remove`", agents.prompts[1])

    def test_a_repair_that_breaks_the_validated_spec_is_undone(self):
        agents = FakeAgents(["valid-contradiction", "broken"])
        self.fake(agents)
        with mock.patch.dict(orc.CFG, oracle_repair_rounds=1):
            r = self.run_oracle()
        self.assertEqual((r["valid"], r["repairs"], r["contradictions"]), (True, 1, ["feature/dsda"]))
        self.assertEqual(self.spec_text(), "valid-contradiction")
        self.assertFalse((self.od.parent / ".o1.validated").exists())

    def test_validation_still_failing_after_the_rounds_is_retried_from_scratch(self):
        agents = FakeAgents(["broken"] * 6)
        self.fake(agents)
        r = self.run_oracle()
        self.assertFalse(r["valid"])
        self.assertIn("after 2 repair round(s)", r["problems"][0])
        self.assertEqual((len(agents.prompts), r["attempts"]), (6, 2))
        self.assertTrue((self.od.parent / "o1.attempt1").is_dir())

    def test_no_session_means_no_repair(self):
        agents = FakeAgents(["broken", "broken"], session=None)
        self.fake(agents)
        r = self.run_oracle()
        self.assertIn("no session to repair", r["problems"][0])
        self.assertEqual(agents.prompts, ["TASK", "TASK"])


class ExtractionAndReuseTest(RunTest):
    def test_an_extraction_failure_keeps_the_spec_and_only_extracts_again(self):
        agents = FakeAgents(["valid"])
        self.fake(agents)
        agents.extract_fails = True
        r = self.run_oracle()
        self.assertEqual((r["valid"], r["needs_extraction"], len(agents.prompts)), (False, True, 1))
        agents.extract_fails = False
        r = self.run_oracle()
        self.assertEqual((r["valid"], r["needs_extraction"], len(agents.prompts)), (True, False, 1))

    def test_a_valid_oracle_is_reused_under_the_same_keys(self):
        agents = FakeAgents(["valid"])
        self.fake(agents)
        self.run_oracle()
        before = agents.extractions
        self.assertTrue(self.run_oracle()["valid"])
        self.assertEqual((len(agents.prompts), agents.extractions), (1, before))

    def test_another_extraction_key_only_extracts_again(self):
        agents = FakeAgents(["valid"])
        self.fake(agents)
        self.run_oracle()
        r = self.run_oracle(("spec-1", "extraction-2"))
        self.assertEqual((r["valid"], r["extraction_key"], len(agents.prompts), agents.extractions),
                         (True, "extraction-2", 1, 4))

    def test_another_spec_key_runs_the_oracle_again(self):
        agents = FakeAgents(["valid", "valid"])
        self.fake(agents)
        self.run_oracle()
        r = self.run_oracle(("spec-2", "extraction-1"))
        self.assertEqual((r["valid"], r["spec_key"], r["attempts"], len(agents.prompts)), (True, "spec-2", 2, 2))


NAMES = {"o1": {"A", "B"}, "o2": {"A", "B", "C"}, "o3": {"A"}}


class FormReferenceTest(RunTest):
    def setUp(self):
        super().setUp()
        self.runs = core.oracle_runs(RUN, self.state)
        for (label, od), voip in zip(self.runs, ("keep", "keep", "remove")):
            (od / "spec" / "openspec").mkdir(parents=True)
            (od / "spec" / "openspec" / "proposal.md").write_text(label, encoding="utf-8")
            common.write_json(od / "guards.json", {"medoid": label})
            common.write_json(od / "metrics.json", {})
            common.write_json(od / "decisions" / "agreed.json", table(voip=voip))
        for p in (mock.patch.object(orc, "hmos_index", return_value={}),
                  mock.patch.object(orc, "shared_idents", return_value=set()),
                  mock.patch.object(orc.dec, "cited_names", lambda spec_root, *a: NAMES[spec_root.parent.name])):
            p.start()
            self.addCleanup(p.stop)

    def test_the_reference_is_the_consensus_with_the_medoid_spec_and_verifies(self):
        orc.form_reference(RUN, self.state, self.runs, VOCAB)
        state = common.load_state(RUN)
        core.verify_frozen(RUN, state)
        od = core.oracle_dir(RUN)
        self.assertEqual((state["frozen"], state["oracle"]["medoid"]), (True, "o1"))
        self.assertEqual(common.read_json(od / "decisions.json")["features"]["voip"]["value"], "keep")
        self.assertEqual((od / "spec" / "openspec" / "proposal.md").read_text(encoding="utf-8"), "o1")
        self.assertEqual(core.reference_names(RUN, {}, set()), {"A", "B"})
        self.assertFalse(os.access(od / "decisions.json", os.W_OK))
        consensus = common.read_json(od / core.CONSENSUS_FILE)
        self.assertEqual((consensus["medoid_dissent"], consensus["per_oracle"]["o3"]["agreement"]), ([], 0.0))

    def test_forming_again_after_a_crash_works_on_read_only_files(self):
        orc.form_reference(RUN, self.state, self.runs, VOCAB)
        with common.state_update(RUN) as st:
            st["frozen"] = False
        orc.form_reference(RUN, self.state, self.runs, VOCAB)
        core.verify_frozen(RUN, common.load_state(RUN))

    def test_a_single_oracle_reference_falls_back_to_its_cited_names(self):
        (core.oracle_dir(RUN) / "spec").mkdir(parents=True)
        with mock.patch.object(core.dec, "cited_names", return_value={"Z"}):
            self.assertEqual(core.reference_names(RUN, {}, set()), {"Z"})


class ExtractGuardTest(RunTest):
    def test_extract_refuses_to_overwrite_an_oracle_extraction(self):
        args = argparse.Namespace(run=RUN, target="oracle/o1", out=None, passes=2)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            orc.cmd_extract(args)


if __name__ == "__main__":
    unittest.main()
