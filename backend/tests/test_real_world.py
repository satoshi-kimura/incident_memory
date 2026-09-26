"""CAPTURED_REAL_WORLD import: sanitization, one memory per cycle, facts only (synthetic export, no real data)."""
import json
import unittest

from app.memory import parse_ts
from app.real_world import FORBIDDEN, build_all
from app.similarity import find_similar

THRESHOLD = 134217728.0
SECRET = {"name": "acme-prod-rds-freeable-memory", "acct": "123456789012", "db": "acme-prod-postgres"}


def item(ts, old, new, values=None, recent=None):
    reason = {"threshold": THRESHOLD, "statistic": "Minimum", "period": 300,
              "evaluatedDatapoints": [{"timestamp": t, "value": v} for t, v in (values or [])],
              "recentDatapoints": recent or []}
    data = {"oldState": {"stateValue": old}, "newState": {"stateValue": new, "stateReasonData": reason,
            "stateReason": f"arn:aws:cloudwatch:ap-northeast-1:{SECRET['acct']}:alarm:{SECRET['name']}"}}
    return {"AlarmName": SECRET["name"], "HistoryItemType": "StateUpdate", "Timestamp": ts,
            "HistorySummary": f"{SECRET['db']}", "HistoryData": json.dumps(data)}


HISTORY = {"AlarmHistoryItems": [
    item("2026-09-21T10:15:00+00:00", "OK", "ALARM", [("2026-09-21T10:00:00+00:00", 120e6), ("2026-09-21T10:05:00+00:00", 118e6), ("2026-09-21T10:10:00+00:00", 121e6)]),
    item("2026-09-21T10:32:00+00:00", "ALARM", "OK", recent=[136e6]),
    item("2026-09-21T14:15:00+00:00", "OK", "ALARM", [("2026-09-21T14:00:00+00:00", 110e6), ("2026-09-21T14:05:00+00:00", 100e6), ("2026-09-21T14:10:00+00:00", 105e6)]),
    item("2026-09-21T16:00:00+00:00", "ALARM", "OK", recent=[140e6]),
]}
POINTS = {"Label": "FreeableMemory", "Datapoints": [
    {"Timestamp": f"2026-09-21T{h:02d}:{m:02d}:00+00:00", "Minimum": 150e6, "Unit": "Bytes"}
    for h in range(8, 17) for m in range(0, 60, 5)]}


class RealWorldImportTest(unittest.TestCase):
    def setUp(self):
        self.memories = build_all(HISTORY, POINTS, collected_at="2026-09-26T09:00:00Z")

    def test_one_memory_per_alarm_cycle(self):
        self.assertEqual([m["id"] for m in self.memories], ["INC-20260921-1015", "INC-20260921-1415"])
        for m in self.memories:
            self.assertEqual(m["source_type"], "CAPTURED_REAL_WORLD")
            self.assertEqual(m["status"], "RECOVERED")
            self.assertLessEqual(parse_ts(m["started_at"]), parse_ts(m["ended_at"]))

    def test_facts_only(self):
        for m in self.memories:
            self.assertEqual(m["changes"], [])
            self.assertEqual(m["suspected_causes"], [])
            self.assertIsNone(m["resolution"])
            self.assertEqual(m["analysis"]["sources"]["cloudtrail"], "not_captured")
            text = json.dumps(m).lower()
            for word in ("deploy", "rollback", "connection pool", "traffic spike", "root cause"):
                self.assertNotIn(word, text)

    def test_sanitized(self):
        blob = json.dumps(self.memories)
        for value in SECRET.values():
            self.assertNotIn(value, blob)
        self.assertIsNone(FORBIDDEN.search(blob))

    def test_real_values_are_kept(self):
        first, second = self.memories
        self.assertEqual(first["trigger"]["threshold"], THRESHOLD)
        self.assertEqual(second["signals"][0]["peak"], 100e6)  # lowest datapoint seen by the alarm
        self.assertEqual(first["ended_at"], "2026-09-21T10:32:00Z")

    def test_recurrence_matches_the_earlier_cycle_with_differences(self):
        first, second = self.memories
        res = find_similar(second, [first], second["analysis"]["sources"])
        top = res["matches"][0]
        self.assertEqual(top["incident_id"], first["id"])
        self.assertIn("change", res["omitted_factors"])                       # no change history captured
        self.assertTrue(any(d.startswith("Recovery took") for d in top["differences"]))
        self.assertEqual(find_similar(first, [second], first["analysis"]["sources"])["matches"], [])  # later never counts


class RealWorldReanalysisTest(unittest.TestCase):
    def test_reanalysis_keeps_the_real_world_label(self):
        from app import analysis, config, store
        config.STORE_BACKEND = "memory"
        config.BEDROCK_CLIENT = "disabled"
        config.COLLECTION_CACHE_SECONDS = 0
        store._store = None
        memories = build_all(HISTORY, POINTS, collected_at="2026-09-26T09:00:00Z")
        for m in memories:
            store.get_store().put(m)
        try:
            again, _ = analysis.analyze(memories[-1]["id"])
        finally:
            config.COLLECTION_CACHE_SECONDS = 60
            store._store = None
        self.assertEqual(again["source_type"], "CAPTURED_REAL_WORLD")
        self.assertEqual(again["analysis"]["similar"][0]["incident_id"], memories[0]["id"])


if __name__ == "__main__":
    unittest.main()
