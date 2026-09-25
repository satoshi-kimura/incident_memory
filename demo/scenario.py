"""Controlled incident generator for the Incident Memory demo workload.

Not reachable from the public application. Run manually during demo preparation
(or by the optional weekly schedule). It only touches the demo function.

Phases (chained by async self-invocation because Lambda runs at most 15 minutes):
  baseline  : steady load (1 request/s) for 8 minutes, then apply a release that shortens the
              downstream timeout to 800 ms and enables 3 retries
  degrade   : keep the same load while the simulated database saturates
              partial mode: 12 minutes (errors below the alarm threshold, then latency and concurrency)
              full mode:    15 minutes (errors reach the alarm threshold), then roll back
  recover   : full mode only - 6 more minutes of load after the rollback
  reset     : partial mode only - wait until the analysis window has passed, then restore the settings

Event: {"mode": "partial" | "full", "not_before": <epoch seconds, optional>}
With not_before, a "wait" phase sleeps (re-chaining every 14 minutes) until that time,
so earlier configuration changes stay outside the next incident's analysis window.
"""
import json
import os
import time
from datetime import datetime, timezone

import boto3

lam = boto3.client("lambda")
TARGET = os.environ["TARGET_FUNCTION"]
SELF = os.environ["AWS_LAMBDA_FUNCTION_NAME"]


def log(msg, **kw):
    print(json.dumps({"msg": msg, **kw}))


def load(minutes, rps=1.0):
    end = time.time() + minutes * 60
    n = 0
    while time.time() < end:
        lam.invoke(FunctionName=TARGET, InvocationType="Event", Payload=b"{}")
        n += 1
        time.sleep(1.0 / rps)
    log("load_done", invocations=n)


def set_release(timeout_ms, retries, version, escalate=False):
    cfg = lam.get_function_configuration(FunctionName=TARGET)
    env = cfg.get("Environment", {}).get("Variables", {})
    env.pop("DB_POOL_SIZE", None)
    env.update({"DOWNSTREAM_TIMEOUT_MS": str(timeout_ms), "MAX_RETRIES": str(retries),
                "ESCALATE": "true" if escalate else "false",
                "RELEASE_VERSION": version, "RELEASE_APPLIED_AT": str(int(time.time()))})
    lam.update_function_configuration(FunctionName=TARGET, Environment={"Variables": env})
    lam.get_waiter("function_updated_v2").wait(FunctionName=TARGET)
    log("release_applied", timeout_ms=timeout_ms, retries=retries, version=version)


def next_phase(event, phase):
    lam.invoke(FunctionName=SELF, InvocationType="Event", Payload=json.dumps({**event, "phase": phase}).encode())


def handler(event, context):
    mode = event.get("mode", "partial")
    phase = event.get("phase", "wait" if event.get("not_before") else "baseline")
    log("phase_start", mode=mode, phase=phase)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d.%H%M")

    if phase == "wait":
        remaining = float(event["not_before"]) - time.time()
        if remaining > 0:
            time.sleep(min(remaining, 14 * 60))
        next_phase(event, "wait" if float(event["not_before"]) > time.time() else "baseline")
    elif phase == "baseline":
        load(8)
        set_release(800, 3, f"v2.14-{stamp}", escalate=(mode == "full"))
        next_phase(event, "degrade")
    elif phase == "degrade":
        if mode == "full":
            load(14.5)
            set_release(3000, 0, f"v2.13-rollback-{stamp}")
            next_phase(event, "recover")
        else:
            load(12)
            next_phase(event, "reset")
    elif phase == "recover":
        load(6)
    elif phase == "reset":
        time.sleep(14 * 60)  # keep the restore outside the incident's analysis window
        set_release(3000, 0, f"v2.13-{stamp}")
    return {"mode": mode, "phase": phase}
