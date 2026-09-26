"""Prerender the key content of the live app into frontend/index.html.

Readers that do not run JavaScript (crawlers, AI scoring systems) then see the
product and a real analyzed incident instead of "Loading…". Browsers replace this
content with the interactive app on load.

  python3 scripts/prerender.py [--api https://d2zs12dmk7373h.cloudfront.net]

Data comes from the public API (read-only). Run it after the live incident is analyzed,
then build and deploy as usual.
"""
import argparse
import math
import json
import re
import subprocess
from datetime import datetime, timezone
from html import escape
from pathlib import Path

INDEX = Path(__file__).resolve().parent.parent / "frontend" / "index.html"
START, END = "<!-- PRERENDER:START -->", "<!-- PRERENDER:END -->"
SOURCE = {"LIVE_DEMO": "Live demo", "CAPTURED_DEMO": "Captured demo", "SEEDED_DEMO": "Seeded demo (fictional)",
          "CAPTURED_REAL_WORLD": "Captured real-world (sanitized)"}
SHORT = {"Errors": "errors", "Duration": "latency", "ConcurrentExecutions": "concurrency", "Throttles": "throttling",
         "Invocations": "traffic", "DatabaseConnections": "DB connections", "FreeableMemory": "DB memory",
         "WriteThrottleEvents": "write throttling"}


def get(api, path):
    out = subprocess.run(["curl", "-sf", api + path], check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def pattern(tokens):
    words = []
    for t in tokens:
        if t.startswith("change:"):
            words.append(f"{t[7:]} change")
        elif t.startswith("alarm:"):
            words.append("alarm")
        else:
            name, direction = t.split(":")
            metric = name.split(".")[-1]
            words.append(SHORT.get(metric, metric) + (" ↓" if direction == "down" else ""))
    return " → ".join(words)


def dt(iso):
    return f"{iso[:10]} {iso[11:16]} UTC" if iso else "not recorded"


def timeline_item(x):
    ev = f" <code>{escape(x['evidence_id'])}</code>" if x.get("evidence_id") else ""
    return (f"<li><code>{escape(x['ts'][11:16])}</code> {escape(x['description'])}{ev}"
            f" <span class=\"faint\">({escape(x['source'])})</span></li>")


def incident_item(x):
    match = x.get("best_match")
    closest = f" · closest match {match['score']}% {escape(match['id'])}" if match else ""
    return (f"<li><code>{escape(x['id'])}</code> {escape(x['title'])} · {escape(SOURCE.get(x['source_type'], ''))}"
            f" · Started {escape(dt(x['started_at']))}{closest}</li>")


def render(api):
    rows = get(api, "/api/incidents")["incidents"]
    featured_row = next((r for r in rows if r["status"] != "RESOLVED" and r.get("best_match")
                         and r["source_type"] != "CAPTURED_REAL_WORLD"), None)
    real_world = [r for r in rows if r["source_type"] == "CAPTURED_REAL_WORLD"]
    recurrence_row = next((r for r in real_world if r.get("best_match")), None)
    e = escape
    parts = ['''<section class="intro">
      <span class="eyebrow">Operational memory for AWS incidents</span>
      <h1>When AWS fails, remember what worked last time.</h1>
      <p>Incident Memory reconstructs an alarm from CloudWatch and CloudTrail, compares it with past failures, and
      surfaces the previous cause, action, and recovery time.</p>
    </section>''']

    if featured_row:
        m = get(api, f"/api/incidents/{featured_row['id']}")
        a = m["analysis"]
        top = a["similar"][0]
        t = m["trigger"]
        causes = top.get("suspected_causes") or []
        cause = next((c for c in causes if c["confidence"] == "HIGH"), causes[0] if causes else None)
        r = top.get("resolution") or {}
        nxt = "; ".join(f"{x['description']}{' fired' if x['token'].startswith('alarm:') else ''} "
                        f"{x['minutes_after_state']:g} min after the {x['after_description']}"
                        for x in top.get("next_events", [])[:2])
        why = "".join(f"<li><b>{e(b['label'])}</b> {'' if b['omitted'] else f'{b['points']:g}/{b['weight']}'}: "
                      f"{e(b['reason'])}</li>" for b in top["breakdown"])
        diff = "".join(f"<li>{e(d)}</li>" for d in top.get("differences", []))
        timeline = "".join(timeline_item(x) for x in m["timeline"])
        ai = (a.get("ai") or {}).get("summary") if a.get("ai_status") == "DONE" else None
        parts.append(f'''<section class="featured-card">
      <div class="featured-copy">
        <div class="row"><span class="eyebrow">Recent analyzed incident · Featured analysis</span><span class="badge">{e(SOURCE.get(m['source_type'], m['source_type']))}</span></div>
        <h2>{e(m['title'])}</h2>
        <p class="muted"><b>Evidence: CloudWatch + CloudTrail</b> · real AWS evidence from the isolated demo environment</p>
        <span class="eyebrow">Closest historical match</span>
        <div class="match-callout" aria-label="{top['score']}% similar to {e(top['incident_id'])}"><span class="match-number">{top['score']}%</span><span><b>similar to {e(top['incident_id'])}</b><small>Different cause, similar failure pattern</small></span></div>
        <div class="pattern-line"><b>Pattern similarity:</b> different cause · <b>Shared pattern:</b> {e(pattern(top.get('shared_sequence', [])))}</div>
        <details class="hero-details"><summary>Why {top['score']}% similar, what differs, and what happened last time</summary>
          <div class="hero-details-body">
            <h3>Why {top['score']}% similar?</h3><ul>{why}</ul>
            <h3>What is different</h3><ul>{diff}</ul>
            <h3>What happened last time?</h3><ul>
              {f"<li>After the same state, {e(nxt)}.</li>" if nxt else ""}
              {f"<li>Previous suspected cause: {e(cause['description'])} ({e(cause['confidence'])})</li>" if cause else ""}
              {f"<li>Previous action: {e(r['action'])}</li>" if r else ""}
              {f"<li>Previous outcome: {e(r['result'])}</li>" if r else ""}
              {f"<li>Recovery time: {r['time_to_recovery_min']} minutes after the alarm</li>" if r else ""}
            </ul>
            {f"<h3>Incident summary (Amazon Bedrock, grounded in the evidence below)</h3><p>{e(ai)}</p>" if ai else ""}
            <h3>Timeline (evidence: CloudWatch + CloudTrail)</h3><ul>{timeline}</ul>
          </div>
        </details>
      </div>
      <div class="featured-action">
        <div class="mini-facts"><span><b>Explainable</b> five-factor score</span><span><b>Grounded</b> evidence IDs</span><span><b>Actionable</b> previous outcome</span></div>
        <a class="btn primary" href="#/incidents/{e(m['id'])}">View featured analysis →</a>
        <span class="small faint mono">{e(m['id'])}</span>
      </div>
    </section>''')

    if recurrence_row:
        m = get(api, f"/api/incidents/{recurrence_row['id']}")
        top = m["analysis"]["similar"][0]
        first = min(r["started_at"] for r in real_world)
        last = max(r["started_at"] for r in real_world)
        days = max(1, math.ceil((datetime.fromisoformat(last.replace("Z", "+00:00"))
                                 - datetime.fromisoformat(first.replace("Z", "+00:00"))).total_seconds() / 86400))
        exact = top.get("match_type") == "exact_recurrence"
        reasons = "".join(f"<li>{e(r)}</li>" for r in top.get("exact_reasons", []))
        diff = "".join(f"<li>{e(d)}</li>" for d in top.get("differences", []))
        gap = top.get("minutes_earlier")
        gap_txt = f"{gap // 60}h {gap % 60}m earlier" if gap is not None else ""
        parts.append(f'''<section class="panel proof-panel">
      <div class="section-head"><div><span class="eyebrow">Captured real-world data · sanitized</span><h2>The same production alarm recurred {len(real_world)} times.</h2></div><span class="badge">Exact recurrence</span></div>
      <div class="proof-stats"><div><strong>{len(real_world)}</strong><span>ALARM → OK cycles</span></div><div><strong>{days} days</strong><span>observed window</span></div><div><strong>Evidence only</strong><span>no invented cause or fix</span></div></div>
      <p class="muted">The same database free-memory failure returned repeatedly. Each occurrence is kept as a separate memory and compared with the previous one.</p>
      <details class="nested-disclosure"><summary>Latest exact recurrence and full evidence</summary><div class="disclosure-body">
        <h3>Latest occurrence: {"EXACT RECURRENCE" if exact else f"{top['score']}% similar"} of {e(top['incident_id'])}, the previous occurrence ({e(gap_txt)})</h3>
        {f"<p>Recurrence score: {top['score']}%. Reasons:</p><ul>{reasons}</ul>" if exact else ""}
        <p>What differed this time:</p><ul>{diff}</ul>
        <p>Outcome: recovered automatically. No resolution recorded. Cause: insufficient evidence.</p>
        <p><b>Evidence: CloudWatch alarm history and metric datapoints</b> (names and identifiers removed; no cause, change or action added).</p>
      </div></details>
    </section>''')

    items = "".join(incident_item(x) for x in rows if x["source_type"] != "CAPTURED_REAL_WORLD")
    parts.append(f'''<details class="panel disclosure">
      <summary><span><b>Browse incident memory</b><small>Historical incidents and captured real-world cycles</small></span></summary>
      <div class="disclosure-body"><ul>{items}</ul>
        {f"<p>Plus {len(real_world)} captured real-world cycles of one production database free-memory alarm.</p>" if real_world else ""}
      </div>
    </details>
    <details class="panel disclosure">
      <summary><span><b>How it works</b><small>AWS architecture, deterministic scoring, and grounded AI</small></span></summary>
      <div class="disclosure-body"><ul>
        <li>Collects bounded evidence from Amazon CloudWatch (alarms, metrics) and AWS CloudTrail (configuration changes)
            for an allowlisted demo workload. AWS workload access is read-only.</li>
        <li>Stores each incident as a structured memory in Amazon DynamoDB: trigger, timeline, signals, changes,
            suspected causes, resolution, and a normalized pattern.</li>
        <li>Scores similarity deterministically: alarm signature 25, service and resource type 20, signal overlap 25,
            event sequence 20, preceding change 10.</li>
        <li>Amazon Bedrock explains the evidence; every suspected cause must cite evidence IDs.</li>
      </ul>
      <p class="small faint">Prerendered from the live API at {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")} UTC
      so the page is readable without JavaScript. The interactive app replaces this content in the browser.</p>
      </div>
    </details>''')
    return "\n    ".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="https://d2zs12dmk7373h.cloudfront.net")
    args = ap.parse_args()
    html = INDEX.read_text()
    block = f"{START}\n    {render(args.api)}\n    {END}"
    if START in html:
        html = re.sub(re.escape(START) + ".*?" + re.escape(END), lambda _: block, html, flags=re.S)
    else:
        html = html.replace('<main id="app"><p class="skeleton">Loading…</p></main>',
                            f'<main id="app">\n    {block}\n  </main>')
    INDEX.write_text(html)
    print(f"prerendered {INDEX}")


if __name__ == "__main__":
    main()
