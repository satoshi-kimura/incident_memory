"""Read-only collection of CloudWatch and CloudTrail evidence.

Layer 2 of the isolation model: queries use only allowlisted names from
config.py, and every result is filtered against the allowlist again before it
is stored, returned to the browser or sent to Bedrock.
"""
import json
import re
import time
from datetime import datetime, timedelta, timezone

import boto3
from botocore.config import Config

from . import config
from .log import log, metric
from .memory import classify_change, iso, parse_ts

_BOTO_CFG = Config(connect_timeout=3, read_timeout=8, retries={"max_attempts": 2, "mode": "standard"})
_clients = {}


class CollectorError(Exception):
    def __init__(self, source, message):
        super().__init__(f"{source}: {message}")
        self.source = source


def _client(name):
    if name not in _clients:
        _clients[name] = boto3.client(name, region_name=config.REGION, config=_BOTO_CFG)
    return _clients[name]


def _fail(source, api, e):
    log("aws_api_failure", level="ERROR", source=source, api=api, error=type(e).__name__, detail=str(e)[:300])
    metric("AwsApiFailures", 1, Source=source)


# --------------------------------------------------------------------------- CloudWatch alarms

_episode_cache = {"at": 0.0, "value": None}


def alarm_transitions(start, end):
    """State transitions of allowlisted demo alarms between start and end."""
    cw = _client("cloudwatch")
    out = []
    try:
        for name in config.DEMO_ALARMS:
            kwargs = {"AlarmName": name, "HistoryItemType": "StateUpdate", "StartDate": start, "EndDate": end,
                      "MaxRecords": 100}
            resp = cw.describe_alarm_history(**kwargs)
            for item in resp["AlarmHistoryItems"]:
                if item["AlarmName"] not in config.DEMO_ALARMS:
                    continue
                data = json.loads(item.get("HistoryData") or "{}")
                new = (data.get("newState") or {})
                out.append({
                    "alarm_name": item["AlarmName"],
                    "ts": iso(item["Timestamp"]),
                    "old": (data.get("oldState") or {}).get("stateValue"),
                    "new": new.get("stateValue"),
                    "value": _reason_value(new.get("stateReason", "")),
                })
    except Exception as e:  # noqa: BLE001
        _fail("cloudwatch", "DescribeAlarmHistory", e)
        raise CollectorError("CloudWatch", "alarm history unavailable") from e
    return sorted(out, key=lambda t: t["ts"])


def _reason_value(reason):
    """Extract the first datapoint value from an AWS-generated state reason, e.g. '[1180.5 (25/09/26 09:07:00)]'."""
    m = re.search(r"\[(-?\d+(?:\.\d+)?) \(", reason or "")
    return float(m.group(1)) if m else None


def discover_episodes(days=14):
    """Group ALARM transitions of demo alarms into incident episodes (cached 60 s).

    Transitions within 20 minutes of the previous one belong to the same episode;
    the earliest is the trigger. The episode ID is derived from the trigger time.
    """
    if _episode_cache["value"] is not None and time.time() - _episode_cache["at"] < 60:
        return _episode_cache["value"]
    end = datetime.now(timezone.utc)
    transitions = alarm_transitions(end - timedelta(days=days), end)
    episodes = []
    for t in (t for t in transitions if t["new"] == "ALARM"):
        if episodes and parse_ts(t["ts"]) - parse_ts(episodes[-1]["alarms"][-1]["ts"]) <= timedelta(minutes=20):
            episodes[-1]["alarms"].append(t)
        else:
            episodes.append({"alarms": [t]})
    for ep in episodes:
        first = ep["alarms"][0]
        ep["id"] = "INC-" + parse_ts(first["ts"]).strftime("%Y%m%d-%H%M")
        ep["trigger_ts"] = first["ts"]
        ep["trigger_alarm"] = first["alarm_name"]
    episodes.reverse()
    _episode_cache.update(at=time.time(), value=episodes)
    return episodes


def describe_alarms():
    cw = _client("cloudwatch")
    try:
        resp = cw.describe_alarms(AlarmNames=config.DEMO_ALARMS, AlarmTypes=["MetricAlarm"])
    except Exception as e:  # noqa: BLE001
        _fail("cloudwatch", "DescribeAlarms", e)
        raise CollectorError("CloudWatch", "alarm definitions unavailable") from e
    out = {}
    for a in resp["MetricAlarms"]:
        if a["AlarmName"] not in config.DEMO_ALARMS:
            continue
        out[a["AlarmName"]] = {
            "metric": a.get("MetricName"),
            "comparison": a.get("ComparisonOperator"),
            "threshold": a.get("Threshold"),
            "statistic": a.get("Statistic"),
            "state": a.get("StateValue"),
        }
    return out


# --------------------------------------------------------------------------- CloudWatch metrics

def collect_metrics(start, end):
    """Return {spec_id: [(iso_ts, value)]} for all watched metrics at 1-minute resolution."""
    cw = _client("cloudwatch")
    queries = [{
        "Id": spec["id"],
        "MetricStat": {
            "Metric": {"Namespace": spec["namespace"], "MetricName": spec["metric"],
                       "Dimensions": config.METRIC_DIMENSIONS},
            "Period": 60,
            "Stat": spec["stat"],
        },
        "ReturnData": True,
    } for spec in config.WATCHED_METRICS]
    series = {spec["id"]: {} for spec in config.WATCHED_METRICS}
    try:
        kwargs = {"MetricDataQueries": queries, "StartTime": start, "EndTime": end, "ScanBy": "TimestampAscending"}
        for _ in range(5):
            resp = cw.get_metric_data(**kwargs)
            for r in resp["MetricDataResults"]:
                if r["Id"] in series:
                    series[r["Id"]].update(zip((iso(t) for t in r["Timestamps"]), r["Values"]))
            if not resp.get("NextToken"):
                break
            kwargs["NextToken"] = resp["NextToken"]
    except Exception as e:  # noqa: BLE001
        _fail("cloudwatch", "GetMetricData", e)
        raise CollectorError("CloudWatch", "metric data unavailable") from e

    # Event-count metrics have no datapoint when nothing happened: fill zeros
    # for minutes where the function was invoked.
    invoked = set(series.get("invocations", {}))
    out = {}
    for spec in config.WATCHED_METRICS:
        pts = series[spec["id"]]
        if spec["metric"] in config.ZERO_FILL_METRICS:
            for ts in invoked:
                pts.setdefault(ts, 0.0)
        out[spec["id"]] = sorted(pts.items())
    return out


# --------------------------------------------------------------------------- CloudTrail

def collect_changes(start, end):
    """Normalized write events for allowlisted demo resources.

    Kept fields: event name, time, service, resource name, caller type. ARNs,
    account IDs, source IPs and request/response payloads are discarded.
    """
    ct = _client("cloudtrail")
    allowed = {r["name"]: r for r in config.CLOUDTRAIL_RESOURCES}
    events = {}
    try:
        for res in config.CLOUDTRAIL_RESOURCES:
            kwargs = {"LookupAttributes": [{"AttributeKey": "ResourceName", "AttributeValue": res["name"]}],
                      "StartTime": start, "EndTime": end, "MaxResults": 50}
            for _ in range(3):
                resp = ct.lookup_events(**kwargs)
                for e in resp.get("Events", []):
                    ev = _normalize_event(e, allowed)
                    if ev:
                        events[ev["event_id"]] = ev
                if not resp.get("NextToken"):
                    break
                kwargs["NextToken"] = resp["NextToken"]
    except Exception as e:  # noqa: BLE001
        _fail("cloudtrail", "LookupEvents", e)
        raise CollectorError("CloudTrail", "event history unavailable") from e
    return sorted(events.values(), key=lambda e: e["ts"])


def _allowlisted(name, allowed):
    """Return the allowlisted resource name for a CloudTrail resource name or ARN, else None."""
    for a in allowed:
        if name == a or name.endswith(":" + a) or name.endswith("/" + a):
            return a
    return None


def _normalize_event(e, allowed):
    if e.get("ReadOnly") == "true":
        return None
    change_category = classify_change(e.get("EventName", ""))
    if not change_category:
        return None
    # Re-filter: every referenced resource must be on the allowlist.
    names = [r.get("ResourceName") for r in e.get("Resources", []) if r.get("ResourceName")]
    matched = [_allowlisted(n, allowed) for n in names]
    if not matched or None in matched:
        return None
    try:
        raw = json.loads(e.get("CloudTrailEvent") or "{}")
    except ValueError:
        raw = {}
    if raw.get("errorCode") or raw.get("awsRegion", config.REGION) != config.REGION:
        return None  # failed calls changed nothing; other regions are out of scope
    # Lambda ARNs with a version/alias suffix (…:function:name:3) are not matched; they fail closed.
    res = allowed[matched[0]]
    return {
        "event_id": e["EventId"],
        "ts": iso(e["EventTime"]),
        "event_name": e["EventName"],
        "service": res["service"],
        "resource": res["name"],
        "resource_type": res["resource_type"],
        "change_category": change_category,
        "caller_type": (raw.get("userIdentity") or {}).get("type"),
    }
