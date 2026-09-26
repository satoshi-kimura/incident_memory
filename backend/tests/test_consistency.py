"""Data consistency rules for every Incident Memory shown in the demo (seeded and live pipeline output)."""
import os
import unittest

os.environ.setdefault("STORE_BACKEND", "memory")

from app import ai, analysis, config, fixture, store  # noqa: E402
from app.memory import parse_ts  # noqa: E402
from app.seed_data import sample_memories  # noqa: E402
from app.similarity import find_similar  # noqa: E402

# Demo alarm thresholds (infra/demo.tf): metric -> threshold
ALARM_THRESHOLDS = {"Duration": 1000, "Errors": 10, "Throttles": 20}


def live_memory():
    config.STORE_BACKEND = "memory"
    config.BEDROCK_CLIENT = "disabled"
    store._store = None
    fixture.install()
    for m in sample_memories():
        store.get_store().put(m)
    eid = next(m["id"] for m in analysis.list_incidents()[0] if m["source_type"] == "LIVE_DEMO")
    return analysis.analyze(eid)[0]


class ConsistencyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.memories = sample_memories() + [live_memory()]

    def test_started_is_alarm_time_and_before_end(self):
        for m in self.memories:
            self.assertEqual(m["started_at"], m["trigger"]["ts"], m["id"])
            if m.get("ended_at"):
                self.assertLessEqual(parse_ts(m["started_at"]), parse_ts(m["ended_at"]), m["id"])

    def test_alarm_and_recovery_events_start_at_the_trigger(self):
        for m in self.memories:
            start = parse_ts(m["started_at"])
            for e in m["timeline"]:
                if e["category"] in ("alarm", "recovery"):
                    self.assertGreaterEqual((parse_ts(e["ts"]) - start).total_seconds(), -60, f"{m['id']} {e}")

    def test_status_matches_end_and_recovery_evidence(self):
        for m in self.memories:
            recovered = [e for e in m["timeline"] if e["category"] == "recovery"]
            if m["status"] == "OPEN":
                self.assertIsNone(m.get("ended_at"), m["id"])
            else:
                self.assertIn(m["status"], ("RECOVERED", "RESOLVED"), m["id"])
                self.assertTrue(m.get("ended_at"), m["id"])
                self.assertTrue(recovered and all(e["evidence_id"] for e in recovered), m["id"])
            if m["status"] == "RESOLVED":
                self.assertTrue(m.get("resolution"), m["id"])

    def test_signals_above_threshold_have_an_alarm(self):
        for m in self.memories:
            alarmed = {e["alarm_token"] for e in m["timeline"] if e["category"] == "alarm" and e.get("alarm_token")}
            for s in m["signals"]:
                limit = ALARM_THRESHOLDS.get(s["metric"])
                if limit is not None and s["service"] == "Lambda" and s["peak"] > limit:
                    self.assertIn(f"alarm:Lambda.{s['metric']}", alarmed,
                                  f"{m['id']}: {s['metric']} peaked at {s['peak']} > {limit} without an alarm")

    def test_alarm_values_exceed_their_thresholds(self):
        for m in self.memories:
            t = m["trigger"]
            if t.get("value") is not None and t.get("threshold") is not None:
                self.assertGreater(t["value"], t["threshold"], m["id"])

    def test_evidence_ids_follow_timeline_order(self):
        for m in self.memories:
            ids = [e["evidence_id"] for e in m["timeline"] if e.get("evidence_id")]
            for prefix in ("CT-", "CW-"):
                seq = [i for i in dict.fromkeys(ids) if i.startswith(prefix)]
                self.assertEqual(seq, sorted(seq), f"{m['id']} {prefix} {seq}")

    def test_references_point_to_existing_evidence(self):
        for m in self.memories:
            ids = {e["id"] for e in m["evidence"]}
            refs = [e["evidence_id"] for e in m["timeline"] if e.get("evidence_id")]
            refs += [i for s in m["signals"] for i in s["evidence_ids"]]
            refs += [i for c in m.get("suspected_causes", []) for i in c["supporting_evidence"]]
            refs += (m.get("resolution") or {}).get("supporting_evidence", [])
            self.assertTrue(set(refs) <= ids, f"{m['id']}: {set(refs) - ids}")

    def test_scores_are_between_0_and_100(self):
        for m in self.memories:
            for r in find_similar(m, self.memories)["matches"]:
                self.assertTrue(0 <= r["score"] <= 100)

    def test_ai_output_cannot_override_the_score(self):
        m = self.memories[-1]
        similar = m["analysis"]["similar"]
        before = [(s["incident_id"], s["score"]) for s in similar]
        out = ai.validate({"summary": "s", "insufficient_evidence": False, "insufficient_evidence_reason": "",
                           "suspected_causes": [], "similarity_explanations": [
                               {"incident_id": similar[0]["incident_id"], "explanation": "This is 100% similar."}]},
                          m, similar)
        self.assertNotIn("score", out)
        self.assertEqual(out["similarity_explanations"], {})  # percentages from the model are dropped
        self.assertEqual(before, [(s["incident_id"], s["score"]) for s in m["analysis"]["similar"]])

    def test_live_demo_matches_inc_0012_around_80_with_a_different_cause(self):
        top = self.memories[-1]["analysis"]["similar"][0]
        self.assertEqual(top["incident_id"], "INC-0012")
        self.assertTrue(75 <= top["score"] <= 88, top["score"])
        self.assertTrue(any(d.startswith("Different change target") for d in top["differences"]))

    def test_source_labels(self):
        from datetime import datetime, timedelta, timezone
        live = self.memories[-1]
        self.assertEqual(live["source_type"], "CAPTURED_DEMO")          # recovered, full window collected
        self.assertTrue(all(e["source"] in ("CloudWatch", "CloudTrail") for e in live["evidence"]))
        for m in sample_memories():
            self.assertEqual(m["source_type"], "SEEDED_DEMO")
        # an incident whose window is still open keeps the LIVE label
        in_progress = {"ended_at": None, "analysis": {"collected_at": datetime.now(timezone.utc).isoformat()}}
        self.assertFalse(analysis.evidence_is_final(in_progress, datetime.now(timezone.utc) + timedelta(minutes=5)))

    def test_landing_page_html_contains_the_demo_without_javascript(self):
        from pathlib import Path
        html = (Path(__file__).resolve().parents[2] / "frontend" / "index.html").read_text()
        static = html.split("<!-- PRERENDER:START -->")[1].split("<!-- PRERENDER:END -->")[0]
        for text in ("Incident Memory", "Your infrastructure remembers what happened last time.",
                     "Recent analyzed incident", "Closest historical match", "% similar to INC-", "Shared pattern",
                     "What happened last time?", "Previous action", "Previous outcome", "CloudWatch + CloudTrail"):
            self.assertIn(text, html if text.startswith(("Incident Memory", "Your infra")) else static, text)

    def test_seeded_evidence_is_labeled_fictional(self):
        for m in sample_memories():
            self.assertEqual(m["source_type"], "SEEDED_DEMO")
            for e in m["evidence"]:
                self.assertIn("fictional", e["source"], m["id"])


if __name__ == "__main__":
    unittest.main()
