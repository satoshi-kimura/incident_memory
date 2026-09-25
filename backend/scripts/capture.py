"""Capture a completed controlled demo incident as a resolved historical memory (CAPTURED_DEMO).

Run during demo preparation, after a "full" scenario (change -> degradation -> rollback).
Evidence is collected from CloudWatch/CloudTrail exactly as in a live analysis; the
operator supplies the resolution notes and the recorded cause, which must cite
evidence IDs present in the collected evidence.

  python -m scripts.capture --episode INC-20260925-0335 --as-id INC-0012 \
      --title "..." --action "..." --result "..." \
      --cause "text|CT-001,CW-001|HIGH"
"""
import argparse
import json
from datetime import timedelta

from app import analysis, collectors
from app.memory import build_pattern, parse_ts
from app.store import get_store

ap = argparse.ArgumentParser()
ap.add_argument("--episode", required=True)
ap.add_argument("--as-id", required=True)
ap.add_argument("--title", required=True)
ap.add_argument("--summary", required=True)
ap.add_argument("--action", required=True)
ap.add_argument("--result", required=True)
ap.add_argument("--cause", action="append", default=[], help="description|EV-1,EV-2|HIGH")
ap.add_argument("--after-min", type=int, default=30)
ap.add_argument("--dry-run", action="store_true")
args = ap.parse_args()

ep = next(e for e in collectors.discover_episodes(days=15) if e["id"] == args.episode)
trigger = parse_ts(ep["trigger_ts"])
memory = analysis.collect_and_build(args.as_id, trigger, ep["trigger_alarm"],
                                    trigger - timedelta(minutes=30), trigger + timedelta(minutes=args.after_min))
assert all(v == "ok" for v in memory["analysis"]["sources"].values()), memory["analysis"]["sources"]

ids = {e["id"] for e in memory["evidence"]}
causes = []
for c in args.cause:
    text, refs, conf = c.split("|")
    refs = refs.split(",")
    assert set(refs) <= ids, f"unknown evidence in {refs}"
    causes.append({"description": text, "supporting_evidence": refs, "confidence": conf, "reasoning": ""})

rollback = [c for c in memory["changes"] if parse_ts(c["ts"]) > trigger]
oks = [e for e in memory["timeline"] if e["category"] == "recovery"]
assert rollback and memory["ended_at"], "incident has not recovered yet"
memory.update({
    "title": args.title,
    "summary": args.summary,
    "source_type": "CAPTURED_DEMO",
    "status": "RESOLVED",
    "suspected_causes": causes,
    "resolution": {
        "action": args.action,
        "ts": rollback[0]["ts"],
        "result": args.result,
        "time_to_recovery_min": round((parse_ts(memory["ended_at"]) - trigger).total_seconds() / 60),
        "supporting_evidence": [rollback[0]["evidence_id"]] + [oks[-1]["evidence_id"]],
    },
    "captured_from": args.episode,
})
memory["timeline"].append({"evidence_id": rollback[0]["evidence_id"], "ts": rollback[0]["ts"], "service": None,
                           "category": "action", "description": args.action, "source": "Operator record"})
memory["timeline"].sort(key=lambda e: (e["ts"], e["category"] != "action"))
memory.pop("analysis")
memory["pattern"] = build_pattern(memory)
print(json.dumps({k: memory[k] for k in ("id", "title", "started_at", "ended_at", "resolution", "pattern")}, indent=2))
print("\n".join(f"{e['id']}: {e['summary']}" for e in memory["evidence"]))
if not args.dry_run:
    get_store().put(memory)
    print("stored", memory["id"])
