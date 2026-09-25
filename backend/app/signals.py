"""Deterministic signal detection from CloudWatch metric series."""
from statistics import median

from . import config
from .memory import iso, magnitude, parse_ts, signal_token, signal_type


def detect_signal(spec, points, anchor_ts, evidence_ids):
    """Detect a sustained change in one metric series.

    spec: entry from config.WATCHED_METRICS
    points: [(iso_ts, value)] sorted by time, 1-minute resolution
    anchor_ts: the baseline is the median of points before this time

    A signal is reported when the value deviates from the baseline by at least
    SIGNAL_REL_THRESHOLD (relative) and spec["abs_min"] (absolute), in the same
    direction, for two consecutive points after the anchor. Returns a dict or None.
    """
    if len(points) < 5:
        return None
    anchor = parse_ts(anchor_ts)
    before = [v for t, v in points if parse_ts(t) < anchor]
    after = [(t, v) for t, v in points if parse_ts(t) >= anchor]
    if len(before) < 3:
        before = [v for _, v in points[:3]]
        after = points[3:]
    if len(after) < 2:
        return None
    baseline = median(before)

    def deviation(v):
        diff = v - baseline
        if abs(diff) < spec["abs_min"]:
            return 0
        if baseline and abs(diff / baseline) < config.SIGNAL_REL_THRESHOLD:
            return 0
        return 1 if diff > 0 else -1

    onset = None
    for i in range(len(after) - 1):
        d = deviation(after[i][1])
        if d and deviation(after[i + 1][1]) == d:
            onset = (after[i][0], d, i)
            break
    if not onset:
        return None

    direction = "up" if onset[1] > 0 else "down"
    tail = after[onset[2]:]
    peak_ts, peak = (max if direction == "up" else min)(tail, key=lambda p: p[1])
    # last point still deviating in the same direction
    until = next((t for t, v in reversed(tail) if deviation(v) == onset[1]), onset[0])
    change_pct = round((peak - baseline) / abs(baseline) * 100, 1) if baseline else None
    return {
        "token": signal_token(config.METRIC_SERVICE, spec["metric"], direction),
        "type": signal_type(spec["metric"], direction),
        "service": config.METRIC_SERVICE,
        "resource": config.METRIC_RESOURCE,
        "resource_type": config.METRIC_RESOURCE_TYPE,
        "metric": spec["metric"],
        "direction": direction,
        "baseline": round(baseline, 3),
        "peak": round(peak, 3),
        "peak_at": iso(peak_ts),
        "change_pct": change_pct,
        "magnitude": magnitude(change_pct),
        "unit": spec["unit"],
        "onset": iso(onset[0]),
        "until": iso(until),
        "evidence_ids": evidence_ids,
    }
