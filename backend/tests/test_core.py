import unittest
from datetime import datetime, timedelta, timezone

from app import ai
from app.memory import build_pattern, classify_change, iso
from app.seed_data import sample_memories
from app.signals import detect_signal
from app.similarity import MATCH_THRESHOLD, compare, find_similar

T0 = datetime(2026, 9, 25, 9, 0, tzinfo=timezone.utc)
FN = "incident-memory-demo-orders-api"


def at(m):
    return iso(T0 + timedelta(minutes=m))


def sig(off, metric, direction="up", service="Lambda", rtype="lambda:function"):
    return {"token": f"{service}.{metric}:{direction}", "service": service, "resource": FN, "resource_type": rtype,
            "metric": metric, "direction": direction, "onset": at(off)}


def current_memory(with_change=True):
    """Live demo pattern: Lambda configuration change -> errors up -> duration up -> concurrency up -> latency alarm."""
    m = {
        "id": "INC-TEST",
        "status": "RECOVERED",
        "trigger": {"service": "Lambda", "metric": "Duration", "comparison": "GreaterThanThreshold", "ts": at(8)},
        "changes": [{"ts": at(0), "change_category": "configuration", "service": "Lambda", "resource": FN,
                     "resource_type": "lambda:function", "event_name": "UpdateFunctionConfiguration20150331v2",
                     "evidence_id": "CT-001"}] if with_change else [],
        "signals": [sig(2, "Errors"), sig(4, "Duration"), sig(6, "ConcurrentExecutions")],
        "timeline": [{"ts": at(8), "category": "alarm", "alarm_token": "alarm:Lambda.Duration"}],
    }
    m["pattern"] = build_pattern(m)
    return m


class SimilarityTest(unittest.TestCase):
    def test_strong_match_is_inc_0012(self):
        res = find_similar(current_memory(), sample_memories())
        self.assertEqual(res["matches"][0]["incident_id"], "INC-0012")
        # Similar pattern, different direct cause and resources: a strong but not identical match
        self.assertTrue(75 <= res["matches"][0]["score"] <= 90, res["matches"][0]["score"])
        for r in res["matches"]:
            self.assertGreaterEqual(r["score"], MATCH_THRESHOLD)

    def test_next_events_reports_errors_alarm_after_latency_alarm(self):
        top = find_similar(current_memory(), sample_memories())["matches"][0]
        nxt = {e["token"]: e for e in top["next_events"]}
        self.assertIn("alarm:Lambda.Errors", nxt)
        self.assertEqual(nxt["alarm:Lambda.Errors"]["minutes_after_state"], 3)

    def test_reasons_name_differences(self):
        top = find_similar(current_memory(), sample_memories())["matches"][0]
        reasons = {b["factor"]: b["reason"] for b in top["breakdown"]}
        self.assertIn("SSM parameter", reasons["change"])
        self.assertIn("only in the historical incident", reasons["resources"])
        self.assertTrue(any(d.startswith("Different change target: Lambda function configuration")
                            for d in top["differences"]), top["differences"])

    def test_shared_pattern_is_change_errors_latency_alarm(self):
        top = find_similar(current_memory(), sample_memories())["matches"][0]
        self.assertEqual(top["shared_sequence"][:4], ["change:configuration", "Lambda.Errors:up",
                                                      "Lambda.Duration:up", "Lambda.ConcurrentExecutions:up"])

    def test_score_is_deterministic(self):
        cur, hist = current_memory()["pattern"], sample_memories()[0]["pattern"]
        s1, b1 = compare(cur, hist)
        self.assertEqual(s1, compare(cur, hist)[0])
        self.assertEqual(sum(f["weight"] for f in b1), 100)
        self.assertAlmostEqual(sum(f["points"] for f in b1), s1, delta=0.6)

    def test_omitted_factors_are_normalized(self):
        cur, hist = current_memory()["pattern"], sample_memories()[0]["pattern"]
        score, b = compare(cur, hist, {"change": "CloudTrail event history unavailable"})
        earned = sum(f["points"] for f in b if not f["omitted"])
        self.assertAlmostEqual(score, 100 * earned / 90, delta=0.6)
        self.assertTrue(next(f for f in b if f["factor"] == "change")["omitted"])

    def test_unrelated_incident_has_no_match(self):
        m = {"id": "X", "status": "OPEN", "changes": [], "timeline": [],
             "trigger": {"service": "S3", "metric": "4xxErrors", "ts": at(3)},
             "signals": [sig(1, "4xxErrors", service="S3", rtype="s3:bucket")]}
        m["pattern"] = build_pattern(m)
        res = find_similar(m, sample_memories())
        self.assertEqual(res["matches"], [])

    def test_open_incidents_are_not_references(self):
        other = current_memory()
        other["id"] = "INC-OTHER"
        other["status"] = "OPEN"
        self.assertEqual(find_similar(current_memory(), [other])["matches"], [])

    def test_only_earlier_recovered_incidents_are_references(self):
        cur = current_memory()
        cur["started_at"] = at(8)
        earlier, later = current_memory(), current_memory()
        earlier.update(id="INC-EARLIER", status="RECOVERED", started_at=at(-60), ended_at=at(-40))
        later.update(id="INC-LATER", status="RECOVERED", started_at=at(60), ended_at=at(80))
        ids = [m["incident_id"] for m in find_similar(cur, [earlier, later])["matches"]]
        self.assertEqual(ids, ["INC-EARLIER"])
        self.assertEqual(find_similar(cur, [earlier])["matches"][0]["recovered_after_min"], 20)


class SignalTest(unittest.TestCase):
    spec = {"id": "duration", "metric": "Duration", "unit": "Milliseconds", "abs_min": 150}

    def test_detects_sustained_increase(self):
        pts = [(at(m), 90 + (m % 3)) for m in range(-10, 3)] + [(at(m), 900) for m in range(3, 8)]
        s = detect_signal(self.spec, pts, at(0), ["CW-001"])
        self.assertEqual(s["direction"], "up")
        self.assertEqual(s["onset"], at(3))

    def test_ignores_single_spike_and_noise(self):
        pts = [(at(m), 90 + (m % 3)) for m in range(-10, 10)]
        pts[12] = (pts[12][0], 2000)
        self.assertIsNone(detect_signal(self.spec, pts, at(0), ["CW-001"]))


class ChangeTest(unittest.TestCase):
    def test_classify(self):
        self.assertEqual(classify_change("UpdateFunctionConfiguration20150331v2"), "configuration")
        self.assertEqual(classify_change("UpdateFunctionCode20150331v2"), "deployment")
        self.assertEqual(classify_change("PutFunctionConcurrency20171031"), "scaling")
        self.assertIsNone(classify_change("GetFunction"))


class AIValidationTest(unittest.TestCase):
    def test_drops_unknown_evidence_and_percentages(self):
        memory = {"evidence": [{"id": "CT-001"}, {"id": "CW-001"}]}
        similar = [{"incident_id": "INC-0012"}]
        out = ai.validate({
            "summary": "Latency rose.",
            "insufficient_evidence": False,
            "insufficient_evidence_reason": "",
            "suspected_causes": [
                {"description": "ok", "supporting_evidence": ["CT-001", "CW-999"], "confidence": "HIGH", "reasoning": "r"},
                {"description": "invented", "supporting_evidence": ["CW-999"], "confidence": "LOW", "reasoning": "r"},
            ],
            "similarity_explanations": [
                {"incident_id": "INC-0012", "explanation": "Same order of events."},
                {"incident_id": "INC-9999", "explanation": "made up"},
            ],
        }, memory, similar)
        self.assertEqual(len(out["suspected_causes"]), 1)
        self.assertEqual(out["suspected_causes"][0]["supporting_evidence"], ["CT-001"])
        self.assertEqual(list(out["similarity_explanations"]), ["INC-0012"])
        pct = ai.validate({"summary": "x", "insufficient_evidence": False, "insufficient_evidence_reason": "",
                           "suspected_causes": [], "similarity_explanations": [
                               {"incident_id": "INC-0012", "explanation": "It is 99% similar."}]}, memory, similar)
        self.assertEqual(pct["similarity_explanations"], {})
        self.assertTrue(pct["insufficient_evidence"])


if __name__ == "__main__":
    unittest.main()
