import os
import unittest

os.environ["STORE_BACKEND"] = "memory"
os.environ["BEDROCK_CLIENT"] = "disabled"

from app import analysis, config, fixture, handler  # noqa: E402
from app.seed_data import sample_memories  # noqa: E402
from app import store  # noqa: E402
from app.store import get_store  # noqa: E402


class PipelineTest(unittest.TestCase):
    def setUp(self):
        config.BEDROCK_CLIENT = "disabled"
        config.STORE_BACKEND = "memory"
        store._store = None
        fixture.install()
        for m in sample_memories():
            get_store().put(m)

    def call(self, method, path):
        import json
        r = handler.lambda_handler({"rawPath": path, "requestContext": {"http": {"method": method}}}, None)
        return r["statusCode"], json.loads(r["body"])

    def test_end_to_end(self):
        status, body = self.call("GET", "/api/incidents")
        self.assertEqual(status, 200)
        new = [r for r in body["incidents"] if r["source_type"] == "LIVE_DEMO"]
        self.assertEqual(len(new), 1)
        status, m = self.call("POST", f"/api/incidents/{new[0]['id']}/analyze")
        self.assertEqual(status, 200)
        # The fixture incident recovered and its whole window was collected: its evidence is now a captured memory.
        self.assertEqual(new[0]["source_type"], "LIVE_DEMO")
        self.assertEqual(m["source_type"], "CAPTURED_DEMO")
        self.assertTrue(m["analysis"]["evidence_final"])
        by_onset = [s["metric"] for s in sorted(m["signals"], key=lambda s: s["onset"])]
        self.assertEqual(by_onset, ["Errors", "Duration", "ConcurrentExecutions"])
        self.assertEqual(m["status"], "RECOVERED")
        self.assertEqual(m["title"], "Orders API latency after Lambda configuration change")
        self.assertEqual(m["changes"][0]["evidence_id"], "CT-001")
        self.assertEqual(m["analysis"]["similar"][0]["incident_id"], "INC-0012")
        self.assertEqual(m["analysis"]["ai_status"], "UNAVAILABLE")
        self.assertTrue(m["analysis"]["rule_based"]["suspected_causes"])
        self.assertNotIn("fingerprint", m["analysis"])
        self.assertIsNotNone(m["ended_at"])

    def test_ai_step_started_once_and_cached(self):
        from app import analysis as an
        config.BEDROCK_CLIENT = "converse"
        calls = []
        orig = an.ai.explain
        an.ai.explain = lambda m, s, src: calls.append(1) or {"summary": "s", "suspected_causes": [],
                                                                "insufficient_evidence": True,
                                                                "insufficient_evidence_reason": "r",
                                                                "similarity_explanations": {}, "dropped_items": 0}
        try:
            eid = [m for m in an.list_incidents()[0] if m["source_type"] == "LIVE_DEMO"][0]["id"]
            config.COLLECTION_CACHE_SECONDS = 0
            m, start = an.analyze(eid)
            self.assertTrue(start)
            an.run_ai(eid, m["analysis"]["fingerprint"])
            m2, start2 = an.analyze(eid)  # identical evidence -> cached, no new Bedrock call
            self.assertFalse(start2)
            self.assertEqual(m2["analysis"]["ai_status"], "DONE")
            self.assertTrue(m2["analysis"]["ai_cached"])
            self.assertEqual(len(calls), 1)
        finally:
            an.ai.explain = orig
            config.BEDROCK_CLIENT = "disabled"
            config.COLLECTION_CACHE_SECONDS = 60

    def test_reanalysis_after_recovery_reuses_stored_evidence(self):
        """After the window is complete, re-analysis must not re-collect (metrics expire after 15 days)."""
        from app import analysis as an, collectors
        eid = [m for m in an.list_incidents()[0] if m["source_type"] == "LIVE_DEMO"][0]["id"]
        first, _ = an.analyze(eid)
        self.assertTrue(first["signals"])
        config.COLLECTION_CACHE_SECONDS = 0
        calls = []
        saved = collectors.collect_metrics, collectors.collect_changes, collectors.alarm_transitions
        def fail(*a, **k):
            calls.append(1)
            raise collectors.CollectorError("CloudWatch", "expired")
        collectors.collect_metrics = collectors.collect_changes = collectors.alarm_transitions = fail
        try:
            again, _ = an.analyze(eid)
        finally:
            collectors.collect_metrics, collectors.collect_changes, collectors.alarm_transitions = saved
            config.COLLECTION_CACHE_SECONDS = 60
        self.assertEqual(calls, [])
        self.assertTrue(again["analysis"]["evidence_final"])
        self.assertEqual(again["signals"], first["signals"])
        self.assertEqual([(s["incident_id"], s["score"]) for s in again["analysis"]["similar"]],
                         [(s["incident_id"], s["score"]) for s in first["analysis"]["similar"]])

    def test_rejects_invalid_ids(self):
        for bad in ["../etc", "arn:aws:lambda:us-east-1:1:function:x", "INC-1", "INC-0012;drop"]:
            status, _ = self.call("GET", f"/api/incidents/{bad}")
            self.assertIn(status, (400, 404))

    def test_historical_not_reanalyzed(self):
        status, _ = self.call("POST", "/api/incidents/INC-0012/analyze")
        self.assertEqual(status, 409)

    def test_unknown_incident(self):
        status, _ = self.call("GET", "/api/incidents/INC-0099")
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
