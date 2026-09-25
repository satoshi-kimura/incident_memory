"""Synthetic collectors for local development and tests only (never deployed as live data).

Simulates the demo scenario: configuration change -> Duration up -> ConcurrentExecutions up -> latency alarm.
"""
from datetime import datetime, timedelta, timezone

from . import collectors
from .memory import iso

T0 = datetime.now(timezone.utc).replace(second=0, microsecond=0) - timedelta(minutes=25)
TRIGGER = T0 + timedelta(minutes=7)


def _series(fn):
    return [(iso(T0 + timedelta(minutes=m)), fn(m)) for m in range(-8, 13)]


def install():
    def discover_episodes(days=14):
        return [{"id": "INC-" + TRIGGER.strftime("%Y%m%d-%H%M"), "trigger_ts": iso(TRIGGER),
                 "trigger_alarm": "incident-memory-demo-orders-api-latency-high",
                 "alarms": []}]

    def describe_alarms():
        return {"incident-memory-demo-orders-api-latency-high":
                {"metric": "Duration", "comparison": "GreaterThanThreshold", "threshold": 1000.0, "state": "OK"}}

    def alarm_transitions(start, end):
        return [
            {"alarm_name": "incident-memory-demo-orders-api-latency-high", "ts": iso(TRIGGER), "old": "OK",
             "new": "ALARM", "value": 1105.2},
            {"alarm_name": "incident-memory-demo-orders-api-latency-high", "ts": iso(T0 + timedelta(minutes=14)),
             "old": "ALARM", "new": "OK", "value": 0.0},
        ]

    def collect_metrics(start, end):
        dur = lambda m: 88 + (m % 3) * 3 if m < 2 else 90 + (m - 1) * 230 if m <= 10 else 90
        return {
            "duration": _series(dur),
            "concurrency": _series(lambda m: 1 if m < 4 else min(6, 1 + (m - 3))),
            "errors": _series(lambda m: 0),
            "throttles": _series(lambda m: 0),
            "invocations": _series(lambda m: 60 + (m % 2)),
        }

    def collect_changes(start, end):
        return [{"event_id": "fixture-1", "ts": iso(T0 + timedelta(seconds=12)),
                 "event_name": "UpdateFunctionConfiguration20150331v2", "service": "Lambda",
                 "resource": "incident-memory-demo-orders-api", "resource_type": "lambda:function",
                 "change_category": "configuration", "caller_type": "AssumedRole"}]

    collectors.discover_episodes = discover_episodes
    collectors.describe_alarms = describe_alarms
    collectors.alarm_transitions = alarm_transitions
    collectors.collect_metrics = collect_metrics
    collectors.collect_changes = collect_changes
