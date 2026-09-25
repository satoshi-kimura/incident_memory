"""Incident Memory model.

An Incident Memory is a JSON document (stored as-is in DynamoDB):

{
  "id": "INC-0012",
  "title": str,
  "source_type": "LIVE_DEMO" | "CAPTURED_DEMO" | "SEEDED_DEMO",
  "status": "RESOLVED" | "OPEN" | "NEW",
  "created_at", "started_at", "ended_at" (or None), "region",
  "trigger": {"alarm_name", "alarm_category", "service", "metric", "comparison",
              "value", "threshold", "unit", "ts"},
  "timeline": [{"evidence_id", "ts", "service", "category", "description", "source"}],
  "signals": [{"token", "type", "service", "resource", "resource_type", "metric", "direction",
               "baseline", "peak", "change_pct", "magnitude", "unit", "onset", "until", "evidence_ids"}],
  "changes": [{"ts", "change_category", "service", "resource", "resource_type", "event_name", "evidence_id"}],
  "suspected_causes": [{"description", "supporting_evidence", "confidence": HIGH|MEDIUM|LOW, "reasoning"}],
  "resolution": {"action", "ts", "result", "time_to_recovery_min", "supporting_evidence"} | None,
  "evidence": [{"id": "CW-001" | "CT-001", "kind", "source", "summary", ...}],
  "pattern": {...}  # normalized features, see build_pattern()
}
"""
import re
from datetime import datetime, timezone

SOURCE_TYPES = ("LIVE_DEMO", "CAPTURED_DEMO", "SEEDED_DEMO")

# CloudTrail event name prefixes -> preceding-change category.
# (Lambda event names carry an API version suffix, e.g. UpdateFunctionConfiguration20150331v2.)
CHANGE_EVENT_PREFIXES = {
    "deployment": ("UpdateFunctionCode", "PublishVersion", "UpdateAlias", "CreateDeployment",
                   "UpdateService", "RegisterTaskDefinition"),
    "configuration": ("UpdateFunctionConfiguration", "PutParameter", "ModifyDBInstance",
                      "ModifyDBParameterGroup", "UpdateTable", "ModifyLoadBalancerAttributes",
                      "ModifyTargetGroup", "UpdateStage"),
    "scaling": ("PutFunctionConcurrency", "DeleteFunctionConcurrency", "PutProvisionedConcurrencyConfig",
                "UpdateAutoScalingGroup", "SetDesiredCapacity", "RegisterScalableTarget"),
}

# Metric name -> alarm/metric family (failure type).
METRIC_FAMILY = {
    "Duration": "latency", "Latency": "latency", "IntegrationLatency": "latency", "TargetResponseTime": "latency",
    "Errors": "errors", "5XXError": "errors", "HTTPCode_Target_5XX_Count": "errors",
    "Throttles": "throttling", "ThrottledRequests": "throttling", "WriteThrottleEvents": "throttling",
    "ConcurrentExecutions": "saturation", "CPUUtilization": "saturation", "FreeableMemory": "saturation",
    "Invocations": "traffic", "Count": "traffic", "RequestCount": "traffic",
}

SIGNAL_TYPES = {
    ("latency", "up"): "latency increased",
    ("errors", "up"): "error rate increased",
    ("throttling", "up"): "throttling increased",
    ("saturation", "up"): "concurrency/saturation increased",
    ("traffic", "up"): "traffic increased",
    ("traffic", "down"): "traffic decreased",
}


def classify_change(event_name):
    for category, prefixes in CHANGE_EVENT_PREFIXES.items():
        if event_name.startswith(prefixes):
            return category
    return None


def short_event_name(event_name):
    """UpdateFunctionConfiguration20150331v2 -> UpdateFunctionConfiguration."""
    return re.sub(r"\d{8}(v\d+)?$", "", event_name)


def metric_family(metric):
    return METRIC_FAMILY.get(metric, "other")


def signal_type(metric, direction):
    fam = metric_family(metric)
    return SIGNAL_TYPES.get((fam, direction), f"{metric} {'increased' if direction == 'up' else 'decreased'}")


def parse_ts(value):
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def iso(dt):
    return parse_ts(dt).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_iso():
    return iso(datetime.now(timezone.utc))


def signal_token(service, metric, direction):
    return f"{service}.{metric}:{direction}"


def alarm_token(service, metric):
    return f"alarm:{service}.{metric}"


def magnitude(change_pct):
    """Readable size of a change relative to baseline."""
    if change_pct is None:
        return "up from zero"
    if change_pct >= 100:
        return f"{1 + change_pct / 100:.1f}x baseline"
    return f"{change_pct:+.0f}% vs baseline"


def preceding_change(memory):
    """Category of the change that preceded the incident.

    The most recent CloudTrail change at or before the first signal onset (or the
    trigger when there are no signals). Without one, a traffic increase that is
    the first signal counts as "traffic"; otherwise "none".
    """
    signals = sorted(memory.get("signals", []), key=lambda s: s["onset"])
    trigger_ts = (memory.get("trigger") or {}).get("ts")
    limit = signals[0]["onset"] if signals else trigger_ts
    changes = [c for c in memory.get("changes", []) if limit is None or c["ts"] <= limit]
    if changes:
        return max(changes, key=lambda c: c["ts"])
    if signals and metric_family(signals[0]["metric"]) == "traffic" and signals[0]["direction"] == "up":
        return {"change_category": "traffic", "ts": signals[0]["onset"]}
    return None


def build_pattern(memory):
    """Derive the normalized features used for similarity comparison.

    Deterministic: depends only on the structured trigger, changes, signals and
    alarm timeline entries of the memory.
    """
    trigger = memory.get("trigger") or {}
    signals = sorted(memory.get("signals", []), key=lambda s: s["onset"])
    pre = preceding_change(memory)

    occurrences = []
    if pre and pre["change_category"] != "traffic":
        occurrences.append((pre["ts"], f"change:{pre['change_category']}"))
    for s in signals:
        occurrences.append((s["onset"], s["token"]))
    for e in memory.get("timeline", []):
        if e.get("category") == "alarm" and e.get("alarm_token"):
            occurrences.append((e["ts"], e["alarm_token"]))
    occurrences.sort(key=lambda o: o[0])

    sequence, first_seen = [], {}
    for ts, token in occurrences:
        if token not in first_seen:
            first_seen[token] = ts
            sequence.append(token)

    anchor_ts = pre["ts"] if pre else (signals[0]["onset"] if signals else None)
    offsets = {}
    if anchor_ts:
        a = parse_ts(anchor_ts)
        offsets = {t: round((parse_ts(ts) - a).total_seconds() / 60.0, 1) for t, ts in first_seen.items()}

    resource_types = {s["resource_type"] for s in signals} | {c["resource_type"] for c in memory.get("changes", [])}
    services = {s["service"] for s in signals} | {c["service"] for c in memory.get("changes", [])}
    if trigger.get("service"):
        services.add(trigger["service"])

    return {
        "trigger": {
            "service": trigger.get("service"),
            "metric": trigger.get("metric"),
            "family": metric_family(trigger["metric"]) if trigger.get("metric") else None,
            "comparison": trigger.get("comparison"),
        },
        "services": sorted(services),
        "resource_types": sorted(resource_types),
        "signals": sorted({s["token"] for s in signals}),
        "sequence": sequence,
        "offsets_min": offsets,
        "preceding_change": pre["change_category"] if pre else "none",
        # Informational only (explains differences; not part of the score)
        "preceding_change_resource": pre.get("resource_type") if pre else None,
    }


RESOURCE_TYPE_NAMES = {
    "lambda:function": "Lambda function",
    "rds:db": "RDS database",
    "rds:db-parameter-group": "RDS parameter group",
    "dynamodb:table": "DynamoDB table",
    "ssm:parameter": "SSM parameter",
}


def describe_resource_type(rtype):
    return RESOURCE_TYPE_NAMES.get(rtype, rtype)


def describe_token(token):
    """Human-readable English for a pattern token."""
    if token.startswith("change:"):
        return f"{token.split(':', 1)[1]} change"
    if token.startswith("alarm:"):
        return f"{token.split(':', 1)[1].replace('.', ' ')} alarm"
    name, direction = token.rsplit(":", 1)
    verb = {"up": "increased", "down": "decreased"}.get(direction, direction)
    return f"{name.replace('.', ' ')} {verb}"


def summary_row(memory):
    """Compact representation for the dashboard list."""
    analysis = memory.get("analysis") or {}
    top = analysis.get("similar") or []
    trigger = memory.get("trigger") or {}
    return {
        "id": memory["id"],
        "title": memory.get("title"),
        "source_type": memory.get("source_type"),
        "status": memory.get("status"),
        "started_at": memory.get("started_at"),
        "ended_at": memory.get("ended_at"),
        "trigger": {"alarm_name": trigger.get("alarm_name"), "alarm_category": trigger.get("alarm_category"),
                    "metric": trigger.get("metric"), "service": trigger.get("service")},
        "analyzed_at": analysis.get("analyzed_at"),
        "best_match": {"id": top[0]["incident_id"], "score": top[0]["score"]} if top else None,
    }
