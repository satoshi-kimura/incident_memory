"""Write the SEEDED_DEMO historical Incident Memories to DynamoDB.

  TABLE_NAME=incident-memory-incidents python -m scripts.seed [--skip INC-0012]
"""
import argparse

from app.seed_data import sample_memories
from app.store import get_store

ap = argparse.ArgumentParser()
ap.add_argument("--skip", nargs="*", default=[], help="IDs not to overwrite (e.g. a captured incident)")
args = ap.parse_args()
store = get_store()
for m in sample_memories():
    if m["id"] in args.skip:
        print("skip", m["id"])
        continue
    store.put(m)
    print("seeded", m["id"], m["title"])
