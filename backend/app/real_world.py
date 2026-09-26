"""Build sanitized CAPTURED_REAL_WORLD Incident Memories from an exported CloudWatch alarm history.

Input (exported by the operator from a production account):
  - alarm history: the DescribeAlarmHistory JSON for one metric alarm (StateUpdate items)
  - datapoints:    the GetMetricStatistics JSON for the alarm's metric (5-minute Minimum)

Each OK -> ALARM -> OK cycle becomes its own memory. Only facts present in the data are used:
the metric, threshold, datapoint values and state transitions. No cause, change or action is
added. Everything that identifies the source system (names, account IDs, ARNs, database
identifiers) is dropped; only the generic names below appear in the output.
"""
import json
import re
from datetime import datetime, timedelta, timezone
from statistics import median

from .memory import alarm_token, build_pattern, iso, parse_ts, renumber_evidence, signal_token

SOURCE_TYPE = "CAPTURED_REAL_WORLD"
ALARM_NAME = "production-db-free-memory-low"       # generic public name
RESOURCE = "production-postgresql"                  # generic public name
SERVICE, METRIC, RTYPE = "RDS", "FreeableMemory", "rds:db"
SOURCE_LABEL = "CloudWatch (captured real-world, sanitized)"
MB = 1024 * 1024

# Anything matching these must never appear in the output.
FORBIDDEN = re.compile(r"arn:aws|\b\d{12}\b|gatepath|dbinstanceidentifier|sns\.|@", re.I)


def mb(value):
    return f"{value / MB:,.1f} MiB"


def load_transitions(history):
    """[(ts, old, new, reason_data)] from a DescribeAlarmHistory export, oldest first."""
    rows = []
    for item in history.get("AlarmHistoryItems", []):
        if item.get("HistoryItemType") != "StateUpdate":
            continue
        data = json.loads(item["HistoryData"])
        new = data.get("newState", {})
        rows.append((iso(item["Timestamp"]), data.get("oldState", {}).get("stateValue"), new.get("stateValue"),
                     new.get("stateReasonData", {})))
    return sorted(rows, key=lambda r: r[0])


def load_points(datapoints):
    """[(iso_ts, minimum_bytes)] sorted, from a GetMetricStatistics export."""
    pts = [(iso(p["Timestamp"]), float(p["Minimum"])) for p in datapoints.get("Datapoints", []) if "Minimum" in p]
    return sorted(pts)


def cycles(transitions):
    """Pair each OK -> ALARM with the following ALARM -> OK."""
    out, open_alarm = [], None
    for ts, old, new, reason in transitions:
        if new == "ALARM":
            open_alarm = (ts, reason)
        elif new == "OK" and old == "ALARM" and open_alarm:
            out.append({"alarm_ts": open_alarm[0], "alarm_reason": open_alarm[1], "ok_ts": ts, "ok_reason": reason})
            open_alarm = None
    return out


def build_memory(cycle, points, index, total, span, collected_at):
    alarm_ts, ok_ts = parse_ts(cycle["alarm_ts"]), parse_ts(cycle["ok_ts"])
    reason = cycle["alarm_reason"]
    threshold = float(reason["threshold"])
    evaluated = sorted(((iso(d["timestamp"]), float(d["value"])) for d in reason.get("evaluatedDatapoints", [])))
    covered = bool(points) and points[0][0] <= iso(alarm_ts - timedelta(minutes=30)) and points[-1][0] >= iso(ok_ts)

    if covered:
        window = [(t, v) for t, v in points if alarm_ts - timedelta(minutes=45) <= parse_ts(t) <= ok_ts]
        below = [(t, v) for t, v in window if v < threshold and parse_ts(t) <= alarm_ts]
        # onset: start of the uninterrupted run below the threshold that led to the alarm
        onset = alarm_ts
        for t, v in reversed([p for p in window if parse_ts(p[0]) <= alarm_ts]):
            if v < threshold:
                onset = parse_ts(t)
            else:
                break
        before = [v for t, v in window if parse_ts(t) < onset][-6:]
        baseline = round(median(before)) if len(before) >= 2 else None
        during = [(t, v) for t, v in window if onset <= parse_ts(t) <= ok_ts] + evaluated
        series = [(t, v) for t, v in points if alarm_ts - timedelta(minutes=45) <= parse_ts(t) <= ok_ts + timedelta(minutes=15)]
    else:
        onset = parse_ts(evaluated[0][0]) if evaluated else alarm_ts
        baseline, during, series = None, list(evaluated), []
    if evaluated:
        onset = min(onset, parse_ts(evaluated[0][0]))  # the alarm itself saw these datapoints below the threshold
    low_ts, low = min(during, key=lambda p: p[1])
    last_below = max((t for t, v in during if v < threshold), default=iso(onset))
    recovered_min = round((ok_ts - alarm_ts).total_seconds() / 60)

    evidence, timeline = [], []
    evidence.append({"id": "CW-S", "kind": "cloudwatch_metric", "source": SOURCE_LABEL, "onset": iso(onset),
                     "summary": f"FreeableMemory (5-minute Minimum) fell below the {mb(threshold)} threshold; lowest {mb(low)}"
                                + (f" (baseline {mb(baseline)})" if baseline else "")})
    timeline.append({"evidence_id": "CW-S", "ts": iso(onset), "service": SERVICE, "category": "metric",
                     "description": evidence[-1]["summary"], "source": SOURCE_LABEL})
    vals = ", ".join(mb(v) for _, v in evaluated)
    evidence.append({"id": "CW-A", "kind": "cloudwatch_alarm", "source": SOURCE_LABEL, "ts": iso(alarm_ts),
                     "alarm_name": ALARM_NAME,
                     "summary": f"Alarm {ALARM_NAME} entered ALARM: 3 of 3 datapoints below {mb(threshold)} ({vals})"})
    timeline.append({"evidence_id": "CW-A", "ts": iso(alarm_ts), "service": SERVICE, "category": "alarm",
                     "description": evidence[-1]["summary"], "source": SOURCE_LABEL,
                     "alarm_token": alarm_token(SERVICE, METRIC)})
    ok_vals = ", ".join(mb(v) for v in cycle["ok_reason"].get("recentDatapoints", [])[-1:])
    evidence.append({"id": "CW-O", "kind": "cloudwatch_alarm", "source": SOURCE_LABEL, "ts": iso(ok_ts),
                     "alarm_name": ALARM_NAME, "state": "OK",
                     "summary": f"Alarm {ALARM_NAME} returned to OK" + (f" (datapoint {ok_vals}, not below the threshold)" if ok_vals else "")})
    timeline.append({"evidence_id": "CW-O", "ts": iso(ok_ts), "service": SERVICE, "category": "recovery",
                     "description": evidence[-1]["summary"], "source": SOURCE_LABEL})

    signal = {"token": signal_token(SERVICE, METRIC, "down"), "type": "database free memory decreased",
              "service": SERVICE, "resource": RESOURCE, "resource_type": RTYPE, "metric": METRIC,
              "direction": "down", "baseline": baseline, "peak": low, "peak_at": low_ts,
              "change_pct": round((low - baseline) / baseline * 100, 1) if baseline else None,
              "magnitude": f"lowest {mb(low)} vs threshold {mb(threshold)}", "unit": "Bytes",
              "onset": iso(onset), "until": last_below, "evidence_ids": ["CW-S"]}
    memory = {
        "id": "INC-" + alarm_ts.strftime("%Y%m%d-%H%M"),
        "title": "Database free-memory alarm with automatic recovery",
        "source_type": SOURCE_TYPE,
        "status": "RECOVERED",
        "created_at": collected_at,
        "started_at": iso(alarm_ts),
        "ended_at": iso(ok_ts),
        "region": "ap-northeast-1",
        "trigger": {"alarm_name": ALARM_NAME, "alarm_category": "saturation", "service": SERVICE, "metric": METRIC,
                    "comparison": "LessThanThreshold", "value": evaluated[-1][1] if evaluated else None,
                    "threshold": threshold, "unit": "Bytes", "ts": iso(alarm_ts), "trigger_evidence_id": "CW-A"},
        "timeline": timeline,
        "signals": [signal],
        "changes": [],
        "suspected_causes": [],
        "resolution": None,
        "summary": (f"Free memory on a production PostgreSQL database fell below the {mb(threshold)} alarm threshold "
                    f"(lowest {mb(low)}). The alarm entered ALARM at {iso(alarm_ts)[11:16]} UTC and returned to OK "
                    f"on its own {recovered_min} minutes later. No resolution was recorded. This is cycle {index} of "
                    f"{total} ALARM/OK cycles of the same alarm between {span[0]} and {span[1]}."),
        "evidence": evidence,
        "series": {METRIC: series},
        "captured": {"from": "CloudWatch alarm history and FreeableMemory datapoints exported by the operator",
                     "sanitized": True, "cycle": index, "cycles_total": total},
        "analysis": {
            "collected_at": collected_at,
            "analyzed_at": collected_at,
            "window": {"start": iso(onset - timedelta(minutes=30)), "end": iso(ok_ts)},
            "sources": {"cloudwatch_alarms": "ok", "cloudwatch_metrics": "ok" if covered else "not_captured",
                        "cloudtrail": "not_captured"},
            "errors": [],
            "evidence_final": True,
        },
    }
    renumber_evidence(memory)
    memory["pattern"] = build_pattern(memory)
    return memory


def build_all(history, datapoints, collected_at=None):
    collected_at = collected_at or iso(datetime.now(timezone.utc))
    points = load_points(datapoints)
    cyc = cycles(load_transitions(history))
    if not cyc:
        return []
    span = (cyc[0]["alarm_ts"][:10], cyc[-1]["ok_ts"][:10])
    memories = [build_memory(c, points, i, len(cyc), span, collected_at) for i, c in enumerate(cyc, 1)]
    leaks = [m["id"] for m in memories if FORBIDDEN.search(json.dumps(m))]
    if leaks:
        raise ValueError(f"sanitization failed for {leaks}")
    return memories
