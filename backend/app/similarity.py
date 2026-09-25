"""Deterministic, explainable similarity between Incident Memory patterns.

score = 100 * sum(weight_i * value_i) / sum(weight_i over available factors)
value_i in [0, 1]. The score is computed here, never by the LLM.
See docs/SIMILARITY.md for the full definition.
"""
from .memory import describe_resource_type, describe_token

WEIGHTS = {
    "trigger": 25,
    "resources": 20,
    "signals": 25,
    "sequence": 20,
    "change": 10,
}
LABELS = {
    "trigger": "Trigger / alarm signature",
    "resources": "AWS service / resource type",
    "signals": "Observed signal overlap",
    "sequence": "Event sequence",
    "change": "Preceding change",
}
MATCH_THRESHOLD = 60
TOP_N = 3


def _jaccard(a, b):
    a, b = set(a), set(b)
    return len(a & b) / len(a | b) if a | b else 0.0


def _trigger(cur, hist):
    c, h = cur["trigger"], hist["trigger"]
    if c.get("service") == h.get("service") and c.get("metric") == h.get("metric"):
        return 1.0, f"Same alarm: {c['service']} {c['metric']} ({c['family']})"
    if c.get("family") and c.get("family") == h.get("family"):
        return 0.7, f"Same alarm family ({c['family']}): {c['metric']} vs {h['metric']}"
    if c.get("service") == h.get("service"):
        return 0.3, f"Alarm on the same service ({c['service']}), different family ({c['family']} vs {h['family']})"
    return 0.0, f"Different alarm ({c['service']} {c['metric']} vs {h['service']} {h['metric']})"


def _names(types):
    return ", ".join(describe_resource_type(t) for t in sorted(types))


def _resources(cur, hist):
    c, h = set(cur["resource_types"]), set(hist["resource_types"])
    parts = [f"Shared: {_names(c & h)}" if c & h else "No shared resource types"]
    if h - c:
        parts.append(f"only in the historical incident: {_names(h - c)}")
    if c - h:
        parts.append(f"only in this incident: {_names(c - h)}")
    return _jaccard(c, h), "; ".join(parts)


def _signals(cur, hist):
    """0.5 * coverage + 0.5 * Jaccard.

    coverage = |C ∩ H| / |C| rewards a historical incident that contains
    everything seen so far (the current incident may be at an earlier stage);
    Jaccard penalizes historical incidents with many unrelated signals.
    """
    c, h = set(cur["signals"]), set(hist["signals"])
    common = sorted(c & h)
    v = 0.5 * (len(common) / len(c)) + 0.5 * _jaccard(c, h)
    if not common:
        return v, "No shared signals"
    reason = f"{len(common)} of {len(c)} current signals also seen: " + ", ".join(describe_token(t) for t in common)
    if h - c:
        reason += "; only in the historical incident: " + ", ".join(describe_token(t) for t in sorted(h - c))
    return v, reason


def _sequence(cur, hist):
    """Order agreement of shared events, scaled by how much of the current sequence is shared."""
    hpos = {t: i for i, t in enumerate(hist["sequence"])}
    common = [t for t in cur["sequence"] if t in hpos]
    if len(common) < 2:
        return 0.0, "Fewer than two shared events; ordering not comparable"
    pairs = [(a, b) for i, a in enumerate(common) for b in common[i + 1:]]
    concordant = sum(1 for a, b in pairs if hpos[a] < hpos[b])
    v = (concordant / len(pairs)) * (len(common) / len(cur["sequence"]))
    order = " → ".join(describe_token(t) for t in common)
    if concordant == len(pairs):
        return v, f"Same ordering of {len(common)} of {len(cur['sequence'])} events: {order}"
    return v, f"{concordant} of {len(pairs)} shared event pairs in the same order"


def _change(cur, hist):
    c, h = cur["preceding_change"], hist["preceding_change"]
    if c == h:
        if c == "none":
            return 1.0, "Neither incident was preceded by a detected change"
        reason = f"Both preceded by a {c} change"
        cr, hr = cur.get("preceding_change_resource"), hist.get("preceding_change_resource")
        if cr and hr and cr != hr:
            reason += (f", but to a different resource ({describe_resource_type(cr)} here, "
                       f"{describe_resource_type(hr)} in the historical incident)")
        return 1.0, reason
    cloudtrail = {"deployment", "configuration", "scaling"}
    if c in cloudtrail and h in cloudtrail:
        return 0.5, f"Both preceded by an AWS change ({c} vs {h})"
    return 0.0, f"Different preceding change ({c} vs {h})"


FACTORS = {"trigger": _trigger, "resources": _resources, "signals": _signals, "sequence": _sequence, "change": _change}


def unavailable_factors(cur, sources):
    """Factors that cannot be calculated because evidence is genuinely unavailable."""
    missing = {}
    if not cur["trigger"].get("metric"):
        missing["trigger"] = "No alarm trigger recorded"
    if sources.get("cloudwatch_metrics") == "error":
        missing["signals"] = "CloudWatch metric data unavailable"
        missing["sequence"] = "CloudWatch metric data unavailable"
    elif not cur["signals"]:
        missing["signals"] = "No significant metric changes detected"
    if sources.get("cloudtrail") == "error":
        missing["change"] = "CloudTrail event history unavailable"
    if not cur["resource_types"]:
        missing["resources"] = "No resources identified"
    return missing


def compare(cur, hist, omitted=None):
    """Return (score 0-100, breakdown) for two patterns."""
    omitted = omitted or {}
    breakdown, earned, possible = [], 0.0, 0
    for key, fn in FACTORS.items():
        if key in omitted:
            breakdown.append({"factor": key, "label": LABELS[key], "weight": WEIGHTS[key], "value": None,
                              "points": None, "omitted": True, "reason": omitted[key]})
            continue
        value, reason = fn(cur, hist)
        earned += WEIGHTS[key] * value
        possible += WEIGHTS[key]
        breakdown.append({"factor": key, "label": LABELS[key], "weight": WEIGHTS[key], "value": round(value, 3),
                          "points": round(WEIGHTS[key] * value, 1), "omitted": False, "reason": reason})
    score = int(round(100 * earned / possible)) if possible else 0
    return score, breakdown


def what_happened_next(cur, hist):
    """Historical events that followed the state shared with the current incident.

    Offsets are measured from the last shared event in the historical incident.
    This is a historical comparison, not a prediction.
    """
    hseq, hoff = hist["sequence"], hist["offsets_min"]
    cur_tokens = set(cur["sequence"])
    shared = [t for t in hseq if t in cur_tokens]
    if not shared:
        return []
    last = shared[-1]
    base = hoff.get(last)
    out = []
    for t in hseq[hseq.index(last) + 1:]:
        if t in cur_tokens or base is None or t not in hoff:
            continue
        out.append({"token": t, "description": describe_token(t), "after_token": last,
                    "after_description": describe_token(last), "minutes_after_state": round(hoff[t] - base, 1)})
    return out


def find_similar(current_memory, candidates, sources=None):
    """Rank resolved historical memories; only matches >= MATCH_THRESHOLD are returned."""
    cur = current_memory["pattern"]
    omitted = unavailable_factors(cur, sources or {})
    results = []
    for m in candidates:
        if m["id"] == current_memory["id"] or m.get("status") != "RESOLVED":
            continue
        score, breakdown = compare(cur, m["pattern"], omitted)
        results.append({
            "incident_id": m["id"],
            "title": m.get("title"),
            "source_type": m.get("source_type"),
            "started_at": m.get("started_at"),
            "score": score,
            "breakdown": breakdown,
            "next_events": what_happened_next(cur, m["pattern"]),
            "pattern": {"offsets_min": m["pattern"]["offsets_min"], "sequence": m["pattern"]["sequence"]},
            "suspected_causes": m.get("suspected_causes", []),
            "resolution": m.get("resolution"),
        })
    results.sort(key=lambda r: (-r["score"], r["incident_id"]))
    return {
        "matches": [r for r in results if r["score"] >= MATCH_THRESHOLD][:TOP_N],
        "compared": len(results),
        "best_below_threshold": next(({"incident_id": r["incident_id"], "score": r["score"]}
                                      for r in results if r["score"] < MATCH_THRESHOLD), None),
        "omitted_factors": omitted,
    }
