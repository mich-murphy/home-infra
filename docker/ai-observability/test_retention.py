from __future__ import annotations

import datetime as dt
import importlib.util
import sys
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
SPEC = importlib.util.spec_from_file_location("retention", HERE / "retention.py")
assert SPEC and SPEC.loader
RETENTION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RETENTION)


class ProtectedRetentionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = dt.datetime(2026, 8, 4, tzinfo=dt.timezone.utc)
        self.old = (self.now - dt.timedelta(days=400)).isoformat()

    def test_old_ordinary_evidence_is_selected_but_active_release_evidence_is_protected(self) -> None:
        records = [
            {"trace_id": "tr-ordinary", "created_at": self.old, "protection": {"state": "ordinary", "decision": "defer", "superseded_at": None, "grace_days": "365"}},
            {"trace_id": "tr-adopted", "created_at": self.old, "protection": {"state": "protected", "decision": "adopt", "superseded_at": None, "grace_days": "365"}},
            {"trace_id": "tr-restricted", "created_at": self.old, "protection": {"state": "protected", "decision": "restrict", "superseded_at": None, "grace_days": "365"}},
        ]

        selection = RETENTION.select_expired_evidence(records, now=self.now)

        self.assertEqual(selection["selected"], ["tr-ordinary"])
        self.assertEqual(selection["protected"], ["tr-adopted", "tr-restricted"])

    def test_superseded_evidence_waits_for_a_365_day_grace_period(self) -> None:
        records = [
            {"trace_id": "tr-recent", "created_at": self.old, "protection": {"state": "protected", "decision": "adopt", "superseded_by": "new", "superseded_at": (self.now - dt.timedelta(days=364)).isoformat(), "successor_valid": True, "grace_days": "365"}},
            {"trace_id": "tr-expired", "created_at": self.old, "protection": {"state": "protected", "decision": "adopt", "superseded_by": "new", "superseded_at": (self.now - dt.timedelta(days=366)).isoformat(), "successor_valid": True, "grace_days": "365"}},
        ]

        selection = RETENTION.select_expired_evidence(records, now=self.now)

        self.assertEqual(selection["selected"], ["tr-expired"])
        self.assertEqual(selection["protected"], ["tr-recent"])

    def test_malformed_protection_reference_fails_safe_for_the_whole_selection(self) -> None:
        records = [
            {"trace_id": "tr-ordinary", "created_at": self.old, "protection": {"state": "ordinary", "decision": "defer", "superseded_at": None, "grace_days": "365"}},
            {"trace_id": "tr-malformed", "created_at": self.old, "protection": {"state": "protected", "decision": "adopt", "superseded_by": "new", "superseded_at": "not-a-date", "successor_valid": True, "grace_days": "365"}},
        ]

        selection = RETENTION.select_expired_evidence(records, now=self.now)

        self.assertEqual(selection["selected"], [])
        self.assertEqual(selection["blocked"], ["tr-malformed: invalid superseded_at"])

    def test_missing_or_inconsistent_summary_protection_metadata_blocks_all_deletion(self) -> None:
        missing = RETENTION.protection_from_tags({})
        inconsistent = RETENTION.protection_from_tags({
            "app.agent.eval.protection": "ordinary",
            "app.agent.eval.owner_decision": "adopt",
            "app.agent.eval.grace_days": "365",
        })
        records = [
            {"trace_id": "tr-missing", "created_at": self.old, "protection": missing},
            {"trace_id": "tr-inconsistent", "created_at": self.old, "protection": inconsistent},
            {"trace_id": "tr-ordinary", "created_at": self.old, "protection": {
                "state": "ordinary", "decision": "defer",
                "superseded_at": None, "grace_days": "365",
            }},
        ]

        selection = RETENTION.select_expired_evidence(records, now=self.now)

        self.assertEqual(selection["selected"], [])
        self.assertEqual(len(selection["blocked"]), 2)

    def test_partial_supersession_link_blocks_all_deletion_until_retry(self) -> None:
        partial = RETENTION.protection_from_tags({
            "app.agent.eval.protection": "protected",
            "app.agent.eval.owner_decision": "adopt",
            "app.agent.eval.grace_days": "365",
            "app.agent.eval.superseded_by": "new-identity",
            "app.agent.eval.superseded_at": "",
        })
        records = [
            {"trace_id": "tr-partial", "created_at": self.old, "protection": partial},
            {"trace_id": "tr-ordinary", "created_at": self.old, "protection": {
                "state": "ordinary", "decision": "defer", "superseded_by": None,
                "superseded_at": None, "grace_days": "365",
            }},
        ]

        selection = RETENTION.select_expired_evidence(records, now=self.now)

        self.assertEqual(selection["selected"], [])
        self.assertEqual(selection["blocked"], ["tr-partial: invalid protection"])

    def test_dangling_or_cross_skill_successor_reference_blocks_all_deletion(self) -> None:
        protections = {
            "old": [{
                "identity": "old", "skill": "bro", "summary_complete": True,
                "state": "protected", "decision": "adopt", "grace_days": "365",
                "superseded_by": "missing", "superseded_at": self.old,
            }],
            "old-cross": [{
                "identity": "old-cross", "skill": "bro", "summary_complete": True,
                "state": "protected", "decision": "adopt", "grace_days": "365",
                "superseded_by": "cross-skill", "superseded_at": self.old,
            }],
            "self": [{
                "identity": "self", "skill": "bro", "summary_complete": True,
                "state": "protected", "decision": "adopt", "grace_days": "365",
                "superseded_by": "self", "superseded_at": self.old,
            }],
            "missing-skill-old": [{
                "identity": "missing-skill-old", "skill": None,
                "summary_complete": True, "state": "protected",
                "decision": "adopt", "grace_days": "365",
                "superseded_by": "missing-skill-new", "superseded_at": self.old,
            }],
            "missing-skill-new": [{
                "identity": "missing-skill-new", "skill": None,
                "summary_complete": True, "state": "protected",
                "decision": "adopt", "grace_days": "365",
                "superseded_by": None, "superseded_at": None,
            }],
            "cycle-a": [{
                "identity": "cycle-a", "skill": "bro", "summary_complete": True,
                "state": "protected", "decision": "adopt", "grace_days": "365",
                "superseded_by": "cycle-b", "superseded_at": self.old,
            }],
            "cycle-b": [{
                "identity": "cycle-b", "skill": "bro", "summary_complete": True,
                "state": "protected", "decision": "adopt", "grace_days": "365",
                "superseded_by": "cycle-a", "superseded_at": self.old,
            }],
            "valid-old": [{
                "identity": "valid-old", "skill": "bro", "summary_complete": True,
                "state": "protected", "decision": "adopt", "grace_days": "365",
                "superseded_by": "valid-new", "superseded_at": self.old,
            }],
            "valid-new": [{
                "identity": "valid-new", "skill": "bro", "summary_complete": True,
                "state": "protected", "decision": "restrict", "grace_days": "365",
                "superseded_by": None, "superseded_at": None,
            }],
            "cross-skill": [{
                "identity": "cross-skill", "skill": "research",
                "summary_complete": True, "state": "protected",
                "decision": "adopt", "grace_days": "365",
                "superseded_by": None, "superseded_at": None,
            }],
        }
        RETENTION.resolve_supersession_references(protections)
        records = [
            {"trace_id": "tr-old", "created_at": self.old,
             "protection": protections["old"][0]},
            {"trace_id": "tr-old-cross", "created_at": self.old,
             "protection": protections["old-cross"][0]},
            {"trace_id": "tr-self", "created_at": self.old,
             "protection": protections["self"][0]},
            {"trace_id": "tr-missing-skill", "created_at": self.old,
             "protection": protections["missing-skill-old"][0]},
            {"trace_id": "tr-cycle-a", "created_at": self.old,
             "protection": protections["cycle-a"][0]},
            {"trace_id": "tr-cycle-b", "created_at": self.old,
             "protection": protections["cycle-b"][0]},
            {"trace_id": "tr-ordinary", "created_at": self.old, "protection": {
                "state": "ordinary", "decision": "defer", "superseded_by": None,
                "superseded_at": None, "grace_days": "365",
            }},
        ]

        selection = RETENTION.select_expired_evidence(records, now=self.now)

        self.assertFalse(protections["old"][0]["successor_valid"])
        self.assertFalse(protections["old-cross"][0]["successor_valid"])
        self.assertFalse(protections["self"][0]["successor_valid"])
        self.assertFalse(protections["missing-skill-old"][0]["successor_valid"])
        self.assertFalse(protections["cycle-a"][0]["successor_valid"])
        self.assertFalse(protections["cycle-b"][0]["successor_valid"])
        self.assertTrue(protections["valid-old"][0]["successor_valid"])
        self.assertEqual(selection["selected"], [])
        self.assertEqual(selection["blocked"], [
            "tr-cycle-a: invalid protection",
            "tr-cycle-b: invalid protection",
            "tr-missing-skill: invalid protection",
            "tr-old-cross: invalid protection",
            "tr-old: invalid protection",
            "tr-self: invalid protection",
        ])

    def test_mlflow_inventory_consumes_every_run_and_trace_page(self) -> None:
        class Page(list):
            def __init__(self, values, token):
                super().__init__(values)
                self.token = token

        class Client:
            def __init__(self):
                self.run_tokens = []
                self.trace_tokens = []

            def search_runs(self, experiment_ids, *, max_results, page_token=None):
                self.run_tokens.append(page_token)
                return Page(["run-1"], "runs-next") if page_token is None else Page(["run-2"], None)

            def search_traces(self, *, locations, max_results, page_token=None):
                self.trace_tokens.append(page_token)
                self.asserted_trace_page_size = max_results
                return Page(["trace-1"], "traces-next") if page_token is None else Page(["trace-2"], None)

        client = Client()

        runs = list(RETENTION.iter_runs(client, "evaluation"))
        traces = list(RETENTION.iter_traces(client, "evaluation"))

        self.assertEqual(runs, ["run-1", "run-2"])
        self.assertEqual(traces, ["trace-1", "trace-2"])
        self.assertEqual(client.run_tokens, [None, "runs-next"])
        self.assertEqual(client.trace_tokens, [None, "traces-next"])
        self.assertEqual(client.asserted_trace_page_size, 500)


if __name__ == "__main__":
    unittest.main()
