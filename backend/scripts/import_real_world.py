"""Import an exported production alarm history as sanitized CAPTURED_REAL_WORLD memories.

  python -m scripts.import_real_world --history alarm-history.json --datapoints datapoints.json \
      [--out ../docs/evidence/captured-real-world.json] [--dry-run]

The raw export files are read locally and never stored in the repository. Each ALARM -> OK
cycle becomes one memory, compared with the memories that happened before it.
"""
import argparse
import json

from app import analysis
from app.real_world import build_all
from app.similarity import find_similar
from app.store import get_store

ap = argparse.ArgumentParser()
ap.add_argument("--history", required=True)
ap.add_argument("--datapoints", required=True)
ap.add_argument("--out", default="../docs/evidence/captured-real-world.json")
ap.add_argument("--dry-run", action="store_true")
args = ap.parse_args()

memories = build_all(json.load(open(args.history)), json.load(open(args.datapoints)))
store = get_store()
hidden = store.hidden_episodes()
existing = [m for m in store.list() if m["id"] not in hidden and m.get("source_type") != "CAPTURED_REAL_WORLD"]

references = list(existing)
for m in memories:  # chronological: each cycle is compared only with what happened before it
    result = find_similar(m, references, m["analysis"]["sources"])
    a = m["analysis"]
    a.update(similar=result["matches"], compared_count=result["compared"],
             best_below_threshold=result["best_below_threshold"], omitted_factors=result["omitted_factors"])
    a["rule_based"] = analysis.rule_based_explanation(m, result["matches"])
    a["fingerprint"] = analysis.fingerprint(m, result["matches"])
    a["ai_status"] = "NOT_REQUESTED"
    references.append(m)
    top = result["matches"][0] if result["matches"] else None
    print(m["id"], m["started_at"][5:16], "->", m["ended_at"][5:16],
          f"lowest {m['signals'][0]['peak'] / 1048576:.1f} MB",
          f"| match {top['incident_id']} {top['score']}%" if top else "| no match ≥ 60%")

public = [{k: v for k, v in m.items() if k != "series"} for m in memories]
json.dump(public, open(args.out, "w"), indent=1)
print(f"{len(memories)} memories; sanitized copy written to {args.out}")
if not args.dry_run:
    for m in memories:
        store.put(m)
    print("stored in", "DynamoDB" if hasattr(store, "table") else "memory store")
