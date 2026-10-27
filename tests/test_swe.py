"""Unit tests of the SWE-bench loop's logic that would corrupt results silently if wrong: which
attempts a stage counts, when a playbook is out of date, the playbook leak check, the leak guard of
an attempt, input fingerprints, the task split, harness reports and the paired statistics.

    cd spec_loop && python3 -m unittest discover -s tests -t .
"""

from __future__ import annotations

import contextlib
import copy
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import lib.common as common
from lib import stats
from swe import core, evaluate, noise, synthesis
from swe.env import container_name, host_port
from swe.pipeline import select_tasks
from swe.solve import leak_check, require_valid


class RunTest(unittest.TestCase):
    """A test with its own runs/ directory and one prepared swe_loop run."""

    run_id = "t"

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = mock.patch.object(common, "RUNS", Path(tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        common.save_state(self.run_id, {"kind": core.RUN_KIND, "backend": "local", "stages": {}, "playbooks": {}})

    def solved(self, stage: str, iids: list[str], samples: int) -> None:
        with common.state_update(self.run_id) as st:
            st["stages"][stage] = {"tasks": iids, "samples": samples}

    def attempt(self, stage: str, iid: str, sample: int, dirname: str | None = None, resolved: bool | None = None,
                patch_sha: str = "p1") -> Path:
        d = core.stage_dir(self.run_id, stage) / iid / (dirname or f"s{sample}")
        common.write_json(d / "attempt.json", {"instance_id": iid, "sample": sample, "valid": True,
                                               "patch_sha256": patch_sha, "patch_lines": 3, "problems": []})
        if resolved is not None:
            common.write_json(d / "eval.json", {"resolved": resolved})
        return d


class StageAttemptsTest(RunTest):
    def test_only_current_attempts_of_the_solved_tasks_and_samples(self):
        self.solved("iter-00", ["a"], 1)
        current = self.attempt("iter-00", "a", 1)
        self.attempt("iter-00", "a", 1, dirname="s1.attempt1")
        self.attempt("iter-00", "a", 2)
        self.attempt("iter-00", "b", 1)
        self.assertEqual([d for _rec, d in evaluate.stage_attempts(self.run_id, "iter-00")], [current])

    def test_a_stage_that_was_never_solved_has_no_attempts(self):
        self.attempt("iter-00", "a", 1)
        self.assertEqual(evaluate.stage_attempts(self.run_id, "iter-00"), [])


class NoiseTest(RunTest):
    def test_outcomes_are_keyed_by_sample(self):
        self.solved("iter-00", ["a", "b"], 2)
        self.attempt("iter-00", "a", 1, resolved=True)
        self.attempt("iter-00", "a", 2)
        self.attempt("iter-00", "b", 2, resolved=False)
        self.assertEqual(noise.outcomes(self.run_id, "iter-00"), {"a": {1: True}, "b": {2: False}})

    def test_no_baseline_without_two_scored_samples(self):
        self.solved("iter-00", ["a"], 2)
        self.attempt("iter-00", "a", 1, resolved=True)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertIsNone(noise.cmd_noise(self.run_id))

    def test_flip_rate_and_per_sample_rates(self):
        self.solved("iter-00", ["a", "b"], 2)
        self.attempt("iter-00", "a", 1, resolved=True)
        self.attempt("iter-00", "a", 2, resolved=False)
        self.attempt("iter-00", "b", 1, resolved=True)
        self.attempt("iter-00", "b", 2, resolved=True)
        with contextlib.redirect_stdout(io.StringIO()):
            result = noise.cmd_noise(self.run_id)
        self.assertEqual(result["flip_rate"], 0.5)
        self.assertEqual(result["resolve_rate_per_sample"], [1.0, 0.5])
        self.assertEqual(result["flipped"], ["a"])


class PlaybookCurrentTest(RunTest):
    def write_report(self, ok: bool = True) -> None:
        common.write_json(core.stage_dir(self.run_id, "iter-00") / "playbook" / "leak_report.json",
                          {"ok": ok, "basis": synthesis.basis(self.run_id, "iter-00")})

    def test_current_until_an_outcome_or_patch_changes(self):
        self.solved("iter-00", ["a"], 1)
        self.attempt("iter-00", "a", 1, resolved=False)
        self.write_report()
        self.assertTrue(synthesis.playbook_current(self.run_id, "iter-00"))
        self.attempt("iter-00", "a", 1, resolved=True)
        self.assertFalse(synthesis.playbook_current(self.run_id, "iter-00"))
        self.write_report()
        self.attempt("iter-00", "a", 1, resolved=True, patch_sha="p2")
        self.assertFalse(synthesis.playbook_current(self.run_id, "iter-00"))

    def test_a_rejected_or_missing_playbook_is_not_current(self):
        self.solved("iter-00", ["a"], 1)
        self.attempt("iter-00", "a", 1, resolved=False)
        self.assertFalse(synthesis.playbook_current(self.run_id, "iter-00"))
        self.write_report(ok=False)
        self.assertFalse(synthesis.playbook_current(self.run_id, "iter-00"))


class RunKindTest(RunTest):
    def test_loop_py_runs_are_refused(self):
        common.save_state("openspec", {"backend": "x"})
        self.assertEqual(core.run_kind("openspec"), "loop.py")
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            core.require_swe_run("openspec")
        core.require_swe_run(self.run_id)

    def test_a_missing_gold_row_stops_the_run(self):
        common.write_json(common.run_dir(self.run_id) / "dataset.json",
                          [{"instance_id": "a", "patch": "x", "FAIL_TO_PASS": '["t1"]'}])
        self.assertEqual(core.gold(self.run_id, "a")["FAIL_TO_PASS"], ["t1"])
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            core.gold(self.run_id, "b")


class LeakLinesTest(unittest.TestCase):
    gold_line = "return self.alias_map[alias] if alias in self.alias_map else default_value"
    terms = {"paths": ["django/db/models/query_utils.py", "query_utils.py"],
             "names": ["resolve_expression", "test_lookup_allows_f"],
             "text": synthesis._norm(gold_line)}

    def flagged(self, text: str) -> list[int]:
        return [e["line"] for e in synthesis.leak_lines(text, self.terms)]

    def test_paths_names_and_copied_code_are_flagged(self):
        text = "\n".join(["# Playbook",
                          "- The bug is often in query_utils.py.",
                          "- Call resolve_expression first.",
                          f"- Use `{self.gold_line}`.",
                          "- Reproduce the issue with a short script before changing code.",
                          "- Run test_lookup_allows_f afterwards."])
        self.assertEqual(self.flagged(text), [2, 3, 4, 6])

    def test_names_match_whole_words_only(self):
        self.assertEqual(self.flagged("- Look at how resolve_expressions are combined."), [])

    def test_limits_and_empty_playbooks(self):
        lim = core.CFG["playbook_limits"]
        problems, _ = synthesis.check_playbook("- rule\n" * (lim["max_lines"] + 1), self.terms)
        self.assertTrue(any("lines" in p for p in problems))
        problems, _ = synthesis.check_playbook("", self.terms)
        self.assertIn("the playbook is empty", problems)

    def test_strip_and_fit(self):
        self.assertEqual(synthesis.strip_lines("a\nb\nc\n", [2]), "a\nc\n")
        lim = core.CFG["playbook_limits"]
        fitted = synthesis.fit("\n".join(["y" * 70] * (lim["max_lines"] + 50)))
        self.assertLessEqual(len(fitted.splitlines()), lim["max_lines"])
        self.assertLessEqual(len(fitted), lim["max_chars"])


def tool_event(tool: str, status: str, exit_code: int | None = None, **inputs) -> dict:
    return {"type": "tool_use", "part": {"tool": tool, "state": {"status": status, "input": inputs,
                                                                 "metadata": {"exit": exit_code}}}}


class LeakCheckTest(unittest.TestCase):
    def test_only_a_web_tool_that_got_through_invalidates(self):
        result = leak_check([tool_event("bash", "completed", 0, command="grep -rn 'https://' django/core/validators.py"),
                             tool_event("bash", "completed", 0, command="curl https://github.com/django/django"),
                             tool_event("webfetch", "error", url="https://example.com")])
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["warnings"]), 3)
        result = leak_check([tool_event("webfetch", "completed", url="https://example.com")])
        self.assertFalse(result["ok"])
        self.assertEqual([v["tool"] for v in result["violations"]], ["webfetch"])


class RequireValidTest(unittest.TestCase):
    def test_an_invalid_attempt_stops_the_stage(self):
        ok = {"instance_id": "a", "sample": 1, "valid": True, "problems": []}
        bad = {"instance_id": "b", "sample": 2, "valid": False, "problems": ["infrastructure: APIError"]}
        require_valid("iter-00", [ok])
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
            require_valid("iter-00", [ok, bad])
        self.assertIn("b/s2: infrastructure: APIError", err.getvalue())


class OutcomeConfigTest(unittest.TestCase):
    def test_operational_keys_do_not_change_the_fingerprint(self):
        base = core.outcome_config(core.CFG)
        cfg = copy.deepcopy(core.CFG)
        cfg["iterations"] += 1
        cfg["harness"]["max_workers"] += 1
        cfg["models"]["student"]["base_url"] = "http://elsewhere:1/v1"
        cfg["server"]["base_url"] = "http://elsewhere:2/v1"
        self.assertEqual(core.json_digest(core.outcome_config(cfg)), core.json_digest(base))
        self.assertIn("timeout_s", base["harness"])
        self.assertIn("id", base["models"]["student"])

    def test_settings_that_change_results_do(self):
        cfg = copy.deepcopy(core.CFG)
        cfg["timeouts_min"]["student"] += 1
        self.assertNotEqual(core.json_digest(core.outcome_config(cfg)), core.json_digest(core.outcome_config(core.CFG)))

    def test_the_live_config_is_not_modified(self):
        before = copy.deepcopy(core.CFG)
        core.outcome_config(core.CFG)
        self.assertEqual(core.CFG, before)


class SelectTasksTest(unittest.TestCase):
    rows = [{"instance_id": f"django__django-{i:05d}", "difficulty": d}
            for i, d in enumerate(["<15 min fix", "15 min - 1 hour", "1-4 hours"] * 10)]

    def test_seeded_disjoint_and_filtered(self):
        with mock.patch.dict(core.CFG["dataset"], train=6, test=3, seed=7,
                             difficulties=["<15 min fix", "15 min - 1 hour"]):
            train, test = select_tasks(list(reversed(self.rows)))
            again = select_tasks(self.rows)
        self.assertEqual((train, test), again)
        ids = [r["instance_id"] for r in train + test]
        self.assertEqual(len(set(ids)), 9)
        self.assertTrue(all(r["difficulty"] != "1-4 hours" for r in train + test))

    def test_too_few_tasks_stops(self):
        with mock.patch.dict(core.CFG["dataset"], train=30, test=5, difficulties=[]), \
                contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            select_tasks(self.rows)


class ParseReportTest(unittest.TestCase):
    def test_report_fields_and_missing_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.json"
            common.write_json(path, {"a": {"resolved": True, "patch_successfully_applied": True, "tests_status": {
                "FAIL_TO_PASS": {"success": ["t1"], "failure": []},
                "PASS_TO_PASS": {"success": ["t3"], "failure": ["t2"]}}}})
            r = evaluate.parse_report(path, "a")
            self.assertEqual((r["resolved"], r["applied"], r["f2p_pass"], r["p2p_fail"]), (True, True, 1, ["t2"]))
            self.assertIsNone(evaluate.parse_report(path, "b")["resolved"])
            self.assertIsNone(evaluate.parse_report(Path(tmp) / "missing.json", "a")["resolved"])


class StatsTest(unittest.TestCase):
    def test_mcnemar_exact(self):
        self.assertAlmostEqual(stats.mcnemar_exact(5, 0), 0.0625)
        self.assertEqual(stats.mcnemar_exact(0, 0), 1.0)
        self.assertEqual(stats.mcnemar_exact(3, 3), 1.0)

    def test_sign_flip(self):
        self.assertAlmostEqual(stats.sign_flip([1.0] * 5), 0.0625)
        self.assertEqual(stats.sign_flip([]), 1.0)
        self.assertEqual(stats.sign_flip([0.0, 0.0]), 1.0)
        self.assertEqual(stats.sign_flip([1.0, -1.0]), 1.0)


class EnvHelpersTest(unittest.TestCase):
    def test_container_names_and_endpoints(self):
        self.assertEqual(container_name("r1", "iter-00", "django__django-11099", "s1"),
                         "swe-r1-iter-00-django__django-11099-s1")
        self.assertEqual(container_name("a/b c"), "swe-a-b-c")
        self.assertEqual(host_port("http://10.0.0.5:30000/v1"), "10.0.0.5:30000")
        self.assertEqual(host_port("https://gpu.example/v1"), "gpu.example:443")


if __name__ == "__main__":
    unittest.main()
