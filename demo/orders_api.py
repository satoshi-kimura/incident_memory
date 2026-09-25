"""Demo workload: a stand-in "orders API" Lambda used only for controlled incidents.

It simulates a downstream database dependency. When DB_POOL_SIZE is raised above
40, the simulated database saturates progressively over the minutes following
RELEASE_APPLIED_AT: latency grows from ~2 minutes after the change and requests
start timing out after ~11 minutes. After 25 minutes the simulation returns to
normal. All effects are visible in real AWS/Lambda metrics (Duration,
ConcurrentExecutions, Errors) and the change itself is a real CloudTrail event.
"""
import os
import random
import time


def handler(event, context):
    pool = int(os.environ.get("DB_POOL_SIZE", "20"))
    applied_at = float(os.environ.get("RELEASE_APPLIED_AT", "0"))
    minutes = (time.time() - applied_at) / 60.0

    latency_ms = random.uniform(70, 100)
    if pool > 40 and 2.0 <= minutes <= 25.0:
        latency_ms += min(2700.0, (minutes - 2.0) * 270.0)
        if minutes >= 11.0 and random.random() < min(0.8, (minutes - 11.0) * 0.25):
            time.sleep(0.2)
            raise RuntimeError("Simulated downstream timeout: connection pool exhausted")
    time.sleep(latency_ms / 1000.0)
    return {"ok": True, "latency_ms": round(latency_ms)}
