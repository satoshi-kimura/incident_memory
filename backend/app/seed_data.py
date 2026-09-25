"""Seeded historical Incident Memories (source_type SEEDED_DEMO).

Fictional incidents for the demo workload "incident-memory-demo-orders-api".
They are labeled SEEDED_DEMO everywhere and are never presented as real
production incidents. Each is defined with minute offsets from its start and
expanded into a full Incident Memory by _build().
"""
from datetime import datetime, timedelta, timezone

from .memory import alarm_token, build_pattern, iso, magnitude, metric_family, signal_token, signal_type

FN = "incident-memory-demo-orders-api"
TABLE = "incident-memory-demo-orders"

SAMPLES = [
    {
        "id": "INC-0012",
        "title": "Orders API latency after configuration change (DB_POOL_SIZE 20 → 80)",
        "summary": ("Release v2.14 changed the function configuration and raised DB_POOL_SIZE from 20 to 80. "
                    "Average duration rose three minutes later and concurrency followed; errors began eight "
                    "minutes after the latency alarm. Rolling back the configuration restored normal behavior."),
        "start": "2026-07-14T22:37:00Z",
        "changes": [
            (0, "configuration", "Lambda", FN, "lambda:function", "UpdateFunctionConfiguration20150331v2",
             "Function configuration updated: release v2.14 (DB_POOL_SIZE 20 → 80)"),
        ],
        "signals": [
            (3, 9, "Lambda", FN, "lambda:function", "Duration", "up", 92, 2140, "Milliseconds"),
            (5, 9, "Lambda", FN, "lambda:function", "ConcurrentExecutions", "up", 1, 6, "Count"),
            (15, 18, "Lambda", FN, "lambda:function", "Errors", "up", 0, 41, "Count"),
        ],
        "alarms": [
            (7, "incident-memory-demo-orders-api-latency-high", "Lambda", "Duration", "GreaterThanThreshold", 1180, 1000, True),
            (16, "incident-memory-demo-orders-api-errors-high", "Lambda", "Errors", "GreaterThanThreshold", 41, 5, False),
        ],
        "causes": [
            ("The configuration change that raised DB_POOL_SIZE preceded the duration increase by three minutes; "
             "larger connection pools saturated the downstream database and slowed each invocation.",
             ["CT-001", "CW-001", "CW-002"], "HIGH"),
            ("Longer invocations increased concurrency until requests exceeded the function timeout, producing errors.",
             ["CW-002", "CW-003"], "MEDIUM"),
        ],
        "resolution": (18, 25, "Rolled back the function configuration to release v2.13 (DB_POOL_SIZE 20).",
                       "Duration and errors returned to baseline; both alarms returned to OK."),
    },
    {
        "id": "INC-0009",
        "title": "Orders API latency after DynamoDB capacity change",
        "summary": ("Provisioned write capacity on the orders table was reduced. Write throttling followed within two "
                    "minutes, Lambda duration increased as the SDK retried, and errors appeared."),
        "start": "2026-06-11T09:20:00Z",
        "changes": [
            (0, "configuration", "DynamoDB", TABLE, "dynamodb:table", "UpdateTable",
             "Table updated: provisioned write capacity 200 → 25"),
        ],
        "signals": [
            (2, 12, "DynamoDB", TABLE, "dynamodb:table", "WriteThrottleEvents", "up", 0, 380, "Count"),
            (3, 12, "Lambda", FN, "lambda:function", "Duration", "up", 95, 1460, "Milliseconds"),
            (6, 12, "Lambda", FN, "lambda:function", "Errors", "up", 0, 22, "Count"),
        ],
        "alarms": [
            (5, "incident-memory-demo-orders-api-latency-high", "Lambda", "Duration", "GreaterThanThreshold", 1090, 1000, True),
        ],
        "causes": [
            ("Reduced write capacity caused throttled writes; SDK retries lengthened each invocation.",
             ["CT-001", "CW-001", "CW-002"], "HIGH"),
        ],
        "resolution": (14, 19, "Restored provisioned write capacity to 200 and switched the table to on-demand.",
                       "Throttling stopped and duration returned to baseline."),
    },
    {
        "id": "INC-0007",
        "title": "Throttling during campaign traffic spike",
        "summary": ("A marketing email campaign roughly quadrupled request volume. Concurrency reached the account "
                    "limit and invocations were throttled. No AWS change event preceded the incident."),
        "start": "2026-05-02T13:05:00Z",
        "changes": [],
        "signals": [
            (0, 20, "Lambda", FN, "lambda:function", "Invocations", "up", 610, 2480, "Count"),
            (1, 20, "Lambda", FN, "lambda:function", "ConcurrentExecutions", "up", 2, 10, "Count"),
            (3, 20, "Lambda", FN, "lambda:function", "Throttles", "up", 0, 312, "Count"),
        ],
        "alarms": [
            (4, "incident-memory-demo-orders-api-throttles-high", "Lambda", "Throttles", "GreaterThanThreshold", 188, 20, True),
        ],
        "causes": [
            ("Campaign traffic increased invocations fourfold and concurrency reached the regional limit.",
             ["CW-001", "CW-002", "CW-003"], "HIGH"),
        ],
        "resolution": (22, 38, "Paused the remaining campaign batches and requested a Lambda concurrency quota increase.",
                       "Throttling stopped once traffic returned to normal levels."),
    },
    {
        "id": "INC-0010",
        "title": "Errors after code deployment — missing environment variable",
        "summary": ("A new code package referenced a PAYMENTS_ENDPOINT environment variable that was not configured. "
                    "Errors started one minute after the deployment."),
        "start": "2026-06-24T16:02:00Z",
        "changes": [
            (0, "deployment", "Lambda", FN, "lambda:function", "UpdateFunctionCode20150331v2",
             "New code package deployed (build 1184)"),
        ],
        "signals": [
            (1, 9, "Lambda", FN, "lambda:function", "Errors", "up", 0, 186, "Count"),
        ],
        "alarms": [
            (2, "incident-memory-demo-orders-api-errors-high", "Lambda", "Errors", "GreaterThanThreshold", 96, 5, True),
        ],
        "causes": [
            ("The deployed code expected an environment variable that the function configuration did not define.",
             ["CT-001", "CW-001"], "HIGH"),
        ],
        "resolution": (9, 11, "Added the missing environment variable to the function configuration.",
                       "Errors stopped immediately after the configuration update."),
    },
    {
        "id": "INC-0015",
        "title": "Throttling after reserved concurrency change",
        "summary": ("Reserved concurrency for the orders function was set to 1 during a cost review. "
                    "Normal traffic was throttled within a minute."),
        "start": "2026-08-05T11:15:00Z",
        "changes": [
            (0, "scaling", "Lambda", FN, "lambda:function", "PutFunctionConcurrency20171031",
             "Reserved concurrency set to 1"),
        ],
        "signals": [
            (1, 8, "Lambda", FN, "lambda:function", "Throttles", "up", 0, 144, "Count"),
        ],
        "alarms": [
            (3, "incident-memory-demo-orders-api-throttles-high", "Lambda", "Throttles", "GreaterThanThreshold", 96, 20, True),
        ],
        "causes": [
            ("A reserved concurrency of 1 was lower than normal concurrent demand.", ["CT-001", "CW-001"], "HIGH"),
        ],
        "resolution": (8, 9, "Removed the reserved concurrency setting.", "Throttling stopped within a minute."),
    },
]


def fmt_value(value, unit):
    if unit == "Milliseconds":
        return f"{value:,.0f} ms"
    if unit == "Percent":
        return f"{value:.0f}%"
    return f"{value:,.0f}"


def _build(spec):
    start = datetime.fromisoformat(spec["start"].replace("Z", "+00:00")).astimezone(timezone.utc)

    def at(minutes):
        return iso(start + timedelta(minutes=minutes))

    evidence, timeline, changes, signals = [], [], [], []
    ct_n = cw_n = 0

    for off, cat, service, resource, rtype, event_name, text in spec["changes"]:
        ct_n += 1
        eid = f"CT-{ct_n:03d}"
        evidence.append({"id": eid, "kind": "cloudtrail_event", "source": "CloudTrail", "summary": text,
                         "event_name": event_name, "service": service, "resource": resource, "ts": at(off)})
        changes.append({"ts": at(off), "change_category": cat, "service": service, "resource": resource,
                        "resource_type": rtype, "event_name": event_name, "evidence_id": eid})
        timeline.append({"evidence_id": eid, "ts": at(off), "service": service, "category": "change",
                         "description": text, "source": "CloudTrail"})

    for off, until, service, resource, rtype, metric, direction, base, peak, unit in spec["signals"]:
        cw_n += 1
        eid = f"CW-{cw_n:03d}"
        pct = round((peak - base) / abs(base) * 100, 1) if base else None
        verb = "increased" if direction == "up" else "decreased"
        text = f"{metric} {verb} from {fmt_value(base, unit)} to {fmt_value(peak, unit)}"
        evidence.append({"id": eid, "kind": "cloudwatch_metric", "source": "CloudWatch", "summary": text,
                         "metric": metric, "service": service, "resource": resource})
        signals.append({"token": signal_token(service, metric, direction), "type": signal_type(metric, direction),
                        "service": service, "resource": resource, "resource_type": rtype, "metric": metric,
                        "direction": direction, "baseline": base, "peak": peak, "change_pct": pct,
                        "magnitude": magnitude(pct), "unit": unit, "onset": at(off), "until": at(until),
                        "evidence_ids": [eid]})
        timeline.append({"evidence_id": eid, "ts": at(off), "service": service, "category": "metric",
                         "description": text, "source": "CloudWatch"})

    trigger = None
    for off, name, service, metric, comparison, value, threshold, is_trigger in spec["alarms"]:
        cw_n += 1
        eid = f"CW-{cw_n:03d}"
        unit = next((s[9] for s in spec["signals"] if s[5] == metric), "Count")
        text = f"Alarm {name} entered ALARM ({metric} {fmt_value(value, unit)} > threshold {fmt_value(threshold, unit)})"
        evidence.append({"id": eid, "kind": "cloudwatch_alarm", "source": "CloudWatch", "summary": text,
                         "alarm_name": name, "ts": at(off)})
        timeline.append({"evidence_id": eid, "ts": at(off), "service": service, "category": "alarm",
                         "description": text, "source": "CloudWatch", "alarm_token": alarm_token(service, metric)})
        if is_trigger:
            trigger = {"alarm_name": name, "alarm_category": metric_family(metric), "service": service,
                       "metric": metric, "comparison": comparison, "value": value, "threshold": threshold,
                       "unit": unit, "ts": at(off)}

    act_off, ok_off, action, result = spec["resolution"]
    cw_n += 1
    ok_id = f"CW-{cw_n:03d}"
    evidence.append({"id": ok_id, "kind": "cloudwatch_alarm", "source": "CloudWatch",
                     "summary": "All incident alarms returned to OK", "ts": at(ok_off)})
    timeline.append({"evidence_id": None, "ts": at(act_off), "service": None, "category": "action",
                     "description": action, "source": "Operator record"})
    timeline.append({"evidence_id": ok_id, "ts": at(ok_off), "service": "CloudWatch", "category": "recovery",
                     "description": "All incident alarms returned to OK", "source": "CloudWatch"})
    timeline.sort(key=lambda e: e["ts"])

    memory = {
        "id": spec["id"],
        "title": spec["title"],
        "source_type": "SEEDED_DEMO",
        "status": "RESOLVED",
        "created_at": at(ok_off),
        "started_at": at(0),
        "ended_at": at(ok_off),
        "region": "us-east-1",
        "trigger": trigger,
        "timeline": timeline,
        "signals": signals,
        "changes": changes,
        "summary": spec["summary"],
        "suspected_causes": [{"description": d, "supporting_evidence": refs, "confidence": c, "reasoning": ""}
                             for d, refs, c in spec["causes"]],
        "resolution": {
            "action": action,
            "ts": at(act_off),
            "result": result,
            "time_to_recovery_min": ok_off - next(a[0] for a in spec["alarms"] if a[7]),
            "supporting_evidence": [ok_id],
        },
        "evidence": evidence,
    }
    memory["pattern"] = build_pattern(memory)
    return memory


def sample_memories():
    return [_build(s) for s in SAMPLES]
