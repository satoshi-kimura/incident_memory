"""Incident analysis pipeline.

1. Resolve the incident from an application-defined ID (never from browser-supplied AWS identifiers).
2. Collect CloudWatch alarms/metrics and CloudTrail changes in a bounded window.
3. Reduce raw data to evidence records (CW-###, CT-###), signals and a timeline.
4. Build the Incident Memory and its pattern; compare against resolved memories.
5. Attach an AI explanation: cached by evidence fingerprint, otherwise produced
   asynchronously by Bedrock. A rule-based explanation is used when AI is unavailable.
"""
import hashlib
import json
import time
from datetime import datetime, timedelta, timezone

from . import ai, collectors, config
from .log import log, metric
from .memory import (alarm_token, build_pattern, describe_token, iso, metric_family, now_iso, parse_ts,
                     renumber_evidence,
                     preceding_change, short_event_name)
from .seed_data import fmt_value
from .signals import detect_signal
from .similarity import find_similar
from .store import get_store


class NotFound(Exception):
    pass


class NotAnalyzable(Exception):
    pass


# --------------------------------------------------------------------------- incidents

def list_incidents():
    """Stored memories plus newly discovered alarm episodes that have not been analyzed yet."""
    store = get_store()
    hidden = store.hidden_episodes()
    memories = [m for m in store.list() if m["id"] not in hidden]
    # Episodes already captured as historical memories are not listed again as live incidents.
    known = ({m["id"] for m in memories} | {m["captured_from"] for m in memories if m.get("captured_from")}
             | hidden)
    warnings = []
    try:
        for ep in collectors.discover_episodes():
            if ep["id"] not in known:
                memories.append(_new_incident(ep))
    except collectors.CollectorError as e:
        warnings.append(f"{e.source} is unavailable; live incidents may be missing.")
    return memories, warnings


def get_incident(incident_id):
    store = get_store()
    if incident_id in store.hidden_episodes():
        raise NotFound(incident_id)
    memory = store.get(incident_id)
    if memory:
        return memory
    for ep in _episodes_or_empty():
        if ep["id"] == incident_id:
            return _new_incident(ep)
    raise NotFound(incident_id)


def _episodes_or_empty():
    try:
        return collectors.discover_episodes()
    except collectors.CollectorError:
        return []


def _new_incident(ep):
    return {
        "id": ep["id"],
        "title": _title({"alarm_category": metric_family(_alarm_metric(ep["trigger_alarm"]) or "")}, [], []),
        "source_type": "LIVE_DEMO",
        "status": "NEW",
        "started_at": ep["trigger_ts"],
        "ended_at": None,
        "region": config.REGION,
        "trigger": {"alarm_name": ep["trigger_alarm"], "ts": ep["trigger_ts"],
                    "alarm_category": metric_family(_alarm_metric(ep["trigger_alarm"]) or ""),
                    "metric": _alarm_metric(ep["trigger_alarm"]), "service": "Lambda"},
    }


def _alarm_metric(alarm_name):
    return {"latency": "Duration", "errors": "Errors", "throttles": "Throttles"}.get(
        alarm_name.removeprefix("incident-memory-demo-orders-api-").removesuffix("-high"))


# --------------------------------------------------------------------------- analysis

def analyze(incident_id):
    """Returns (memory, start_ai): start_ai is True when a new asynchronous Bedrock step must be started."""
    started = time.time()
    store = get_store()
    if incident_id in store.hidden_episodes():
        raise NotFound(incident_id)
    existing = store.get(incident_id)
    if existing and (existing.get("source_type") == "SEEDED_DEMO" or existing.get("status") == "RESOLVED"):
        raise NotAnalyzable("Historical incidents are stored memories and are not re-collected from AWS.")
    if existing and time.time() - parse_ts(existing["analysis"]["collected_at"]).timestamp() < config.COLLECTION_CACHE_SECONDS:
        return existing, False

    if existing is None and any(m.get("captured_from") == incident_id for m in store.list()):
        raise NotAnalyzable("This demo incident is not available for analysis.")
    episode = next((e for e in _episodes_or_empty() if e["id"] == incident_id), None)
    if episode is None and existing is None:
        raise NotFound(incident_id)
    trigger_ts = parse_ts(episode["trigger_ts"] if episode else existing["trigger"]["ts"])
    trigger_alarm = episode["trigger_alarm"] if episode else existing["trigger"]["alarm_name"]

    start = trigger_ts - timedelta(minutes=config.WINDOW_BEFORE_MIN)
    window_end = trigger_ts + timedelta(minutes=config.WINDOW_AFTER_MIN)
    if existing and evidence_is_final(existing, window_end):
        # The incident recovered and its whole window was collected. Re-collecting can only lose data
        # (1-minute metrics expire after 15 days), so re-analysis compares the stored evidence again.
        memory = existing
        memory["analysis"]["evidence_final"] = True
        memory["analysis"]["analyzed_at"] = now_iso()
    else:
        memory = collect_and_build(incident_id, trigger_ts, trigger_alarm, start, min(window_end, datetime.now(timezone.utc)))
        if existing:
            memory["created_at"] = existing.get("created_at", memory["created_at"])
        memory["analysis"]["evidence_final"] = evidence_is_final(memory, window_end)
    if memory["analysis"]["evidence_final"]:
        # Evidence was collected from the demo environment and is now kept as a memory.
        memory["source_type"] = "CAPTURED_DEMO"

    history = [m for m in store.list() if m["id"] != incident_id]
    sources = memory["analysis"]["sources"]
    similar = find_similar(memory, history, sources)
    memory["analysis"]["similar"] = similar["matches"]
    memory["analysis"]["compared_count"] = similar["compared"]
    memory["analysis"]["best_below_threshold"] = similar["best_below_threshold"]
    memory["analysis"]["omitted_factors"] = similar["omitted_factors"]
    memory["analysis"]["rule_based"] = rule_based_explanation(memory, similar["matches"])

    requested = None
    fp = fingerprint(memory, similar["matches"])
    memory["analysis"]["fingerprint"] = fp
    cached = store.get_ai(fp)
    if cached:
        memory["analysis"]["ai"] = cached
        memory["analysis"]["ai_status"] = "DONE"
        memory["analysis"]["ai_cached"] = True
    elif config.BEDROCK_CLIENT == "disabled":
        memory["analysis"]["ai_status"] = "UNAVAILABLE"
        memory["analysis"]["ai_error"] = "AI explanation is disabled in this environment."
    elif (existing and existing["analysis"].get("fingerprint") == fp
          and existing["analysis"].get("ai_status") == "PENDING"
          and time.time() - parse_ts(existing["analysis"].get("ai_requested_at", now_iso())).timestamp() < 180):
        # Still running. A PENDING state older than 3 minutes means the async step died and is retried below.
        memory["analysis"]["ai_status"] = "PENDING"
        memory["analysis"]["ai_requested_at"] = existing["analysis"]["ai_requested_at"]
    elif (existing and existing["analysis"].get("fingerprint") == fp
          and existing["analysis"].get("ai_status") == "UNAVAILABLE"
          and time.time() - parse_ts(existing["analysis"]["analyzed_at"]).timestamp() < config.AI_RETRY_AFTER_SECONDS):
        memory["analysis"]["ai_status"] = "UNAVAILABLE"
        memory["analysis"]["ai_error"] = existing["analysis"].get("ai_error")
        memory["analysis"]["analyzed_at"] = existing["analysis"]["analyzed_at"]
    elif not store.take_bedrock_call(config.BEDROCK_DAILY_CALL_LIMIT):
        memory["analysis"]["ai_status"] = "UNAVAILABLE"
        memory["analysis"]["ai_error"] = "Daily AI analysis limit reached. Showing rule-based analysis."
    else:
        memory["analysis"]["ai_status"] = "PENDING"
        memory["analysis"]["ai_requested_at"] = requested = now_iso()

    memory["analysis"]["duration_ms"] = int((time.time() - started) * 1000)
    store.put(memory)
    log("analysis_complete", incident_id=incident_id, duration_ms=memory["analysis"]["duration_ms"],
        sources=sources, matches=[(m["incident_id"], m["score"]) for m in similar["matches"]], ai_status=memory["analysis"]["ai_status"])
    metric("AnalysisDurationMs", memory["analysis"]["duration_ms"], unit="Milliseconds")
    return memory, requested is not None


def evidence_is_final(memory, window_end):
    """True when the incident recovered and its full analysis window was collected."""
    collected = memory.get("analysis", {}).get("collected_at")
    return bool(memory.get("ended_at") and collected and parse_ts(collected) >= window_end)


def run_ai(incident_id, fp):
    """Asynchronous step: call Bedrock for a stored memory and cache the result by fingerprint."""
    store = get_store()
    memory = store.get(incident_id)
    if not memory or memory["analysis"].get("fingerprint") != fp:
        return
    try:
        result = ai.explain(memory, memory["analysis"]["similar"], memory["analysis"]["sources"])
        result["model_id"] = config.BEDROCK_MODEL_ID
        result["generated_at"] = now_iso()
        store.put_ai(fp, result)
        status, error = "DONE", None
    except ai.AIUnavailable as e:
        result, status, error = None, "UNAVAILABLE", f"AI explanation unavailable ({e}). Showing rule-based analysis."
    memory = store.get(incident_id)  # re-read: a newer analysis may have replaced it
    if memory and memory["analysis"].get("fingerprint") == fp:
        memory["analysis"]["ai"] = result
        memory["analysis"]["ai_status"] = status
        memory["analysis"]["ai_error"] = error
        store.put(memory)


def fingerprint(memory, matches):
    """Hash of everything the AI explanation depends on. Same evidence -> same cached result."""
    basis = {
        "trigger": {k: memory["trigger"].get(k) for k in ("alarm_name", "metric", "value", "threshold", "ts")},
        "changes": [{k: c[k] for k in ("ts", "event_name", "change_category", "resource")} for c in memory["changes"]],
        "signals": [{k: s[k] for k in ("token", "baseline", "peak", "onset", "until")} for s in memory["signals"]],
        "timeline": [(e["ts"], e["category"], e["description"]) for e in memory["timeline"]],
        "sources": memory["analysis"]["sources"],
        "matches": [(m["incident_id"], m["score"]) for m in matches],
        "model": config.BEDROCK_MODEL_ID,
        "prompt": config.PROMPT_VERSION,
    }
    return hashlib.sha256(json.dumps(basis, sort_keys=True, default=str).encode()).hexdigest()[:32]


# --------------------------------------------------------------------------- collection

def collect_and_build(incident_id, trigger_ts, trigger_alarm, start, end):
    sources = {"cloudwatch_alarms": "ok", "cloudwatch_metrics": "ok", "cloudtrail": "ok"}
    errors = []

    try:
        alarm_defs = collectors.describe_alarms()
        transitions = collectors.alarm_transitions(start, end)
    except collectors.CollectorError as e:
        alarm_defs, transitions = {}, []
        sources["cloudwatch_alarms"] = "error"
        errors.append(str(e))
    try:
        series = collectors.collect_metrics(start, end)
    except collectors.CollectorError as e:
        series = {}
        sources["cloudwatch_metrics"] = "error"
        errors.append(str(e))
    try:
        ct_events = collectors.collect_changes(start, end)
    except collectors.CollectorError as e:
        ct_events = []
        sources["cloudtrail"] = "error"
        errors.append(str(e))

    evidence, timeline, changes, signals = [], [], [], []
    for i, ev in enumerate(ct_events, 1):
        eid = f"CT-{i:03d}"
        text = f"{short_event_name(ev['event_name'])} on {ev['resource']} ({ev['change_category']} change)"
        evidence.append({"id": eid, "kind": "cloudtrail_event", "source": "CloudTrail", "summary": text,
                         "event_name": ev["event_name"], "resource": ev["resource"], "ts": ev["ts"],
                         "caller_type": ev["caller_type"]})
        changes.append({"ts": ev["ts"], "change_category": ev["change_category"], "service": ev["service"],
                        "resource": ev["resource"], "resource_type": ev["resource_type"],
                        "event_name": ev["event_name"], "evidence_id": eid})
        timeline.append({"evidence_id": eid, "ts": ev["ts"], "service": ev["service"], "category": "change",
                         "description": text, "source": "CloudTrail"})

    # Baseline anchor: the most recent change before the trigger, else 10 minutes before the trigger.
    before_trigger = [c for c in changes if parse_ts(c["ts"]) <= trigger_ts]
    anchor = before_trigger[-1]["ts"] if before_trigger else iso(trigger_ts - timedelta(minutes=10))
    cw_n = 0
    for spec in config.WATCHED_METRICS:
        pts = series.get(spec["id"], [])
        cw_n += 1
        eid = f"CW-{cw_n:03d}"
        s = detect_signal(spec, pts, anchor, [eid])
        if not s:
            cw_n -= 1
            continue
        verb = "increased" if s["direction"] == "up" else "decreased"
        text = (f"{spec['metric']} {verb} from {fmt_value(s['baseline'], spec['unit'])} to "
                f"{fmt_value(s['peak'], spec['unit'])} ({s['magnitude']})")
        evidence.append({"id": eid, "kind": "cloudwatch_metric", "source": "CloudWatch", "summary": text,
                         "metric": spec["metric"], "stat": spec["stat"], "unit": spec["unit"],
                         "baseline": s["baseline"], "peak": s["peak"], "onset": s["onset"], "until": s["until"]})
        signals.append(s)
        timeline.append({"evidence_id": eid, "ts": s["onset"], "service": "Lambda", "category": "metric",
                         "description": text, "source": "CloudWatch"})

    trigger = {"alarm_name": trigger_alarm, "ts": iso(trigger_ts), "service": "Lambda"}
    for t in transitions:
        if t["new"] not in ("ALARM", "OK") or (t["new"] == "OK" and t["old"] != "ALARM"):
            continue
        if parse_ts(t["ts"]) < trigger_ts - timedelta(minutes=1):
            continue  # state changes before this incident's trigger belong to an earlier episode
        cw_n += 1
        eid = f"CW-{cw_n:03d}"
        d = alarm_defs.get(t["alarm_name"], {})
        m = d.get("metric") or _alarm_metric(t["alarm_name"])
        unit = next((s["unit"] for s in config.WATCHED_METRICS if s["metric"] == m), "Count")
        if t["new"] == "ALARM":
            val = f"{m} {fmt_value(t['value'], unit)}" if t["value"] is not None else m
            thr = f", threshold {fmt_value(d['threshold'], unit)}" if d.get("threshold") is not None else ""
            text = f"Alarm {t['alarm_name']} entered ALARM ({val}{thr})"
            category = "alarm"
        else:
            text = f"Alarm {t['alarm_name']} returned to OK"
            category = "recovery"
        evidence.append({"id": eid, "kind": "cloudwatch_alarm", "source": "CloudWatch", "summary": text,
                         "alarm_name": t["alarm_name"], "state": t["new"], "ts": t["ts"]})
        entry = {"evidence_id": eid, "ts": t["ts"], "service": "Lambda", "category": category,
                 "description": text, "source": "CloudWatch"}
        if category == "alarm":
            entry["alarm_token"] = alarm_token("Lambda", m)
        timeline.append(entry)
        if t["alarm_name"] == trigger_alarm and t["new"] == "ALARM" and "value" not in trigger:
            trigger.update({"metric": m, "alarm_category": metric_family(m), "comparison": d.get("comparison"),
                            "threshold": d.get("threshold"), "value": t["value"], "unit": unit,
                            "trigger_evidence_id": eid})
    if "metric" not in trigger:
        m = alarm_defs.get(trigger_alarm, {}).get("metric") or _alarm_metric(trigger_alarm)
        trigger.update({"metric": m, "alarm_category": metric_family(m or ""),
                        "threshold": alarm_defs.get(trigger_alarm, {}).get("threshold")})

    timeline.sort(key=lambda e: (e["ts"], e["evidence_id"] or ""))
    ended = _ended_at(transitions, trigger_ts)

    memory = {
        "id": incident_id,
        "title": _title(trigger, changes, signals),
        "source_type": "LIVE_DEMO",
        # RECOVERED: every alarm returned to OK but no resolution was recorded. OPEN: still in ALARM.
        "status": "RECOVERED" if ended else "OPEN",
        "created_at": now_iso(),
        "started_at": iso(trigger_ts),
        "ended_at": ended,
        "region": config.REGION,
        "trigger": trigger,
        "timeline": timeline,
        "signals": signals,
        "changes": changes,
        "suspected_causes": [],
        "resolution": None,
        "evidence": evidence,
        "series": {spec["metric"]: series.get(spec["id"], []) for spec in config.WATCHED_METRICS},
        "analysis": {
            "collected_at": now_iso(),
            "analyzed_at": now_iso(),
            "window": {"start": iso(start), "end": iso(end)},
            "sources": sources,
            "errors": errors,
        },
    }
    renumber_evidence(memory)
    memory["pattern"] = build_pattern(memory)
    return memory


def _ended_at(transitions, trigger_ts):
    """Time the last alarm returned to OK, if every alarm that fired has recovered."""
    last_state, last_ok = {}, None
    for t in transitions:
        if parse_ts(t["ts"]) < trigger_ts - timedelta(minutes=1):
            continue
        last_state[t["alarm_name"]] = t["new"]
        if t["new"] == "OK":
            last_ok = t["ts"]
    fired = list(last_state)
    if fired and all(last_state[a] == "OK" for a in fired):
        return last_ok
    return None


def _title(trigger, changes, signals):
    family = trigger.get("alarm_category") or "alarm"
    what = {"latency": "Orders API latency", "errors": "Orders API errors", "throttling": "Orders API throttling"}.get(
        family, "Orders API alarm")
    before = [c for c in changes if c["ts"] <= trigger.get("ts", "")]
    if before:
        return f"{what} after {before[-1]['service']} {before[-1]['change_category']} change"
    return f"{what} alarm"


# --------------------------------------------------------------------------- rule-based fallback

def rule_based_explanation(memory, matches):
    """Deterministic explanation used when Bedrock is unavailable. Never invents a cause."""
    signals = sorted(memory["signals"], key=lambda s: s["onset"])
    pre = preceding_change(memory)
    causes = []
    if pre and pre.get("evidence_id") and signals:
        first = signals[0]
        lag = round((parse_ts(first["onset"]) - parse_ts(pre["ts"])).total_seconds() / 60)
        if 0 <= lag <= 15:
            top = matches[0] if matches else None
            change_factor = next((b for b in top["breakdown"] if b["factor"] == "change"), {}) if top else {}
            earlier = [c for c in memory["changes"] if c["ts"] < pre["ts"]]
            same_history = bool(top and change_factor.get("value") == 1.0
                                and any(c["confidence"] == "HIGH" for c in top["suspected_causes"]))
            causes.append({
                "description": (f"The {pre['change_category']} change ({short_event_name(pre['event_name'])}) "
                                f"may have contributed: {describe_token(first['token'])} {lag} minutes later."),
                "supporting_evidence": [pre["evidence_id"]] + [e for s in signals for e in s["evidence_ids"]],
                "confidence": "MEDIUM" if same_history else "LOW",
                "reasoning": ("Temporal ordering only: this is the most recent change before the first signal"
                              + (f"; {len(earlier)} earlier change(s) in the window preceded it without effect."
                                 if earlier else "; no other change was recorded in the window.")
                              + (f" {top['incident_id']} followed the same pattern." if same_history else "")),
            })
    if not signals and not memory["changes"]:
        summary = "The alarm fired, but no significant metric change or AWS change event was found in the analysis window."
    else:
        parts = []
        if pre and pre.get("evidence_id"):
            parts.append(f"A {pre['change_category']} change was recorded at {pre['ts'][11:16]} UTC.")
        if signals:
            parts.append("Observed: " + "; ".join(f"{describe_token(s['token'])} at {s['onset'][11:16]}"
                                                   for s in signals) + ".")
        if matches:
            parts.append(f"The pattern resembles {matches[0]['incident_id']}.")
        summary = " ".join(parts)
    return {
        "summary": summary,
        "suspected_causes": causes,
        "insufficient_evidence": not causes,
        "insufficient_evidence_reason": "" if causes else "No change event clearly preceded the observed signals.",
    }
