"""Unit tests of how the reference is formed from several oracles (lib/consensus.py).

    cd spec_loop && python3 -m unittest discover -s tests -t .
"""

from __future__ import annotations

import unittest

from lib import consensus as cons
from lib import decisions as dec

VALUES = {"keep": "保留", "remove": "移除", "unstated": "未表态"}
VOCAB = {"kinds": {
    "features": {"label": "功能", "question": "?", "values": VALUES,
                 "items": {"voip": {"label": "VoIP", "agents_value": None},
                           "dsda": {"label": "DSDA", "agents_value": "remove"}}},
    **{kind: {"label": kind, "question": "?", "values": VALUES, "items": {}}
       for kind in ("macros", "dependencies", "architecture")}}}


def table(tag: str = "", **values) -> dict:
    """A clean extraction table: every vocabulary key, the given ones stated with a quote."""
    out = {kind: {} for kind in dec.KINDS}
    for kind, key, _item, _allowed in dec.vocab_items(VOCAB):
        v = values.get(key)
        out[kind][key] = {"value": None} if v is None else \
            {"value": v, "evidence": [{"file": "proposal.md", "quote": f"{key} {v} {tag}"}], "files": []}
    return out


def value(t: dict, key: str):
    return t["features"][key]["value"]


class AgreedTableTest(unittest.TestCase):
    def test_disagreeing_passes_abstain(self):
        agreed = cons.agreed_table(table(voip="keep", dsda="remove"), table(voip="keep", dsda="keep"), VOCAB)
        self.assertEqual(value(agreed, "voip"), "keep")
        self.assertIsNone(value(agreed, "dsda"))

    def test_a_key_neither_pass_states_stays_unstated(self):
        self.assertIsNone(value(cons.agreed_table(table(), table(), VOCAB), "voip"))


class ConsensusValuesTest(unittest.TestCase):
    def values(self, *voip):
        return cons.consensus_values([table(voip=v) for v in voip], VOCAB)

    def test_two_of_three_is_a_majority(self):
        cv = self.values("keep", "keep", "remove")
        self.assertEqual(cv["values"]["features"]["voip"], "keep")
        self.assertEqual(cv["contested"], [])
        self.assertEqual(cv["votes"]["feature/voip"], ["keep", "keep", "remove"])

    def test_a_split_or_a_single_voice_is_contested(self):
        for votes in (("keep", "remove", None), ("keep", None, None)):
            cv = self.values(*votes)
            self.assertIsNone(cv["values"]["features"]["voip"])
            self.assertEqual(cv["contested"], ["feature/voip"])

    def test_nobody_stating_a_key_is_not_contested(self):
        cv = self.values(None, None, None)
        self.assertIsNone(cv["values"]["features"]["voip"])
        self.assertEqual(cv["contested"], [])

    def test_a_settled_key_takes_agents_md_value_when_a_majority_addresses_it(self):
        cv = cons.consensus_values([table(dsda="keep"), table(dsda="keep"), table()], VOCAB)
        self.assertEqual(cv["values"]["features"]["dsda"], "remove")
        self.assertEqual(cv["overrides"], ["feature/dsda"])
        cv = cons.consensus_values([table(dsda="remove"), table(dsda="remove"), table()], VOCAB)
        self.assertEqual((cv["values"]["features"]["dsda"], cv["overrides"]), ("remove", []))

    def test_a_settled_key_a_minority_addresses_is_contested(self):
        cv = cons.consensus_values([table(dsda="remove"), table(), table()], VOCAB)
        self.assertIsNone(cv["values"]["features"]["dsda"])
        self.assertEqual((cv["contested"], cv["overrides"]), (["feature/dsda"], []))


class ContestedNotScoredTest(unittest.TestCase):
    def test_compare_skips_keys_without_a_reference_value(self):
        cv = cons.consensus_values([table(voip="keep", dsda="remove"), table(voip="remove", dsda="remove"),
                                    table(dsda="remove")], VOCAB)
        ref = cons.consensus_table([table(voip="keep", dsda="remove")] * 3, cv["values"], 0, ["o1", "o2", "o3"], VOCAB)
        items = dec.compare(ref, table(voip="keep", dsda="remove"), {"modules": {}}, {"modules": {}}, VOCAB,
                            {"idents": set()})
        self.assertEqual([it["id"] for it in items], ["feature/dsda"])


class AgentsContradictionsTest(unittest.TestCase):
    def test_only_settled_keys_stated_otherwise(self):
        found = cons.agents_contradictions(table(voip="remove", dsda="keep"), VOCAB)
        self.assertEqual([(c["id"], c["value"], c["agents_value"]) for c in found], [("feature/dsda", "keep", "remove")])
        self.assertEqual(found[0]["quotes"], ["dsda keep "])
        self.assertEqual(cons.agents_contradictions(table(dsda="remove"), VOCAB), [])


class NamesAndMedoidTest(unittest.TestCase):
    def test_names_cited_by_a_majority(self):
        self.assertEqual(cons.consensus_names([{"A", "B"}, {"A", "C"}, {"A", "B", "D"}]), {"A", "B"})

    def test_medoid_by_agreement_then_names_then_index(self):
        tables = [table(voip="remove"), table(voip="keep"), table(voip="keep")]
        values = cons.consensus_values(tables, VOCAB)["values"]
        self.assertEqual([cons.agreement(t, values, VOCAB) for t in tables], [0.0, 1.0, 1.0])
        self.assertEqual(cons.pick_medoid([(0.0, 1.0), (1.0, 1.0), (1.0, 1.0)]), 1)
        self.assertEqual(cons.pick_medoid([(0.0, 1.0), (1.0, 0.5), (1.0, 1.0)]), 2)

    def test_dissent_lists_keys_stated_otherwise_or_not_at_all(self):
        values = cons.consensus_values([table(voip="keep", dsda="remove")] * 3, VOCAB)["values"]
        self.assertEqual(cons.dissent(table(voip="remove"), values, VOCAB), ["feature/voip", "feature/dsda"])
        self.assertEqual(cons.dissent(table(voip="keep", dsda="remove"), values, VOCAB), [])

    def test_evidence_comes_from_the_medoid_else_the_first_holder(self):
        tables = [table("o1", voip="remove", dsda="keep"), table("o2", voip="keep", dsda="keep"),
                  table("o3", voip="keep")]
        cv = cons.consensus_values(tables, VOCAB)
        ref = cons.consensus_table(tables, cv["values"], 2, ["o1", "o2", "o3"], VOCAB)
        self.assertEqual((ref["features"]["voip"]["source"], ref["features"]["voip"]["evidence"][0]["quote"]),
                         ("o3", "voip keep o3"))
        ref = cons.consensus_table(tables, cv["values"], 0, ["o1", "o2", "o3"], VOCAB)
        self.assertEqual(ref["features"]["voip"]["source"], "o2")
        self.assertEqual((ref["features"]["dsda"]["value"], ref["features"]["dsda"]["source"]), ("remove", "AGENTS.md"))

    def test_report_renders(self):
        report = {"oracles": ["o1", "o2", "o3"], "majority": 2, "medoid": "o2", "stated": 1,
                  "contested": ["feature/voip"], "overrides": [], "medoid_dissent": [],
                  "votes": {"feature/voip": ["keep", "remove", None]}, "names": ["A"],
                  "per_oracle": {o: {"agreement": 1.0, "names_jaccard": 0.5} for o in ("o1", "o2", "o3")}}
        md = cons.render_md(report)
        self.assertIn("o2", md)
        self.assertIn("| feature/voip | keep | remove | - |", md)


if __name__ == "__main__":
    unittest.main()
