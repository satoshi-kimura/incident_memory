"""Demo workload: a stand-in "orders API" Lambda used only for controlled incidents.

It simulates calls to a downstream service. A release that shortens the downstream
timeout (DOWNSTREAM_TIMEOUT_MS below 1000) while enabling retries (MAX_RETRIES > 0)
causes a retry storm:

  +2 min   a small share of requests time out and fail (Errors rise, below the errors alarm threshold)
  +4 min   retries pile up on the downstream service and latency grows (Duration, then concurrency)
  +12 min  only when ESCALATE=true (set by the full scenario): most requests fail and the errors alarm fires

After 25 minutes the simulation returns to normal. All effects are visible in real
AWS/Lambda metrics, and the configuration change itself is a real CloudTrail event.
"""
import os
import random
import time

_calls = 0


def handler(event, context):
    global _calls
    _calls += 1
    timeout_ms = int(os.environ.get("DOWNSTREAM_TIMEOUT_MS", "3000"))
    retries = int(os.environ.get("MAX_RETRIES", "0"))
    applied_at = float(os.environ.get("RELEASE_APPLIED_AT", "0"))
    escalate = os.environ.get("ESCALATE") == "true"
    minutes = (time.time() - applied_at) / 60.0

    latency_ms = random.uniform(70, 100)
    if timeout_ms < 1000 and retries > 0 and 2.0 <= minutes <= 25.0:
        if escalate and minutes >= 12.0 and random.random() < min(0.8, (minutes - 12.0) * 0.25):
            time.sleep(0.2)
            raise RuntimeError("Simulated downstream timeout after retries")
        if _calls % 12 == 0:  # about 5 failures per minute at 1 request per second, below the alarm threshold of 10
            time.sleep(0.1)
            raise RuntimeError("Simulated downstream timeout")
        if minutes >= 4.0:
            latency_ms += min(2700.0, (minutes - 4.0) * 320.0)
    time.sleep(latency_ms / 1000.0)
    return {"ok": True, "latency_ms": round(latency_ms)}
