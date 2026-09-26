"""Prerender the key content of the live app into frontend/index.html.

Readers that do not run JavaScript (crawlers, AI scoring systems) then see the
product and a real analyzed incident instead of "Loading…". Browsers replace this
content with the interactive app on load.

  python3 scripts/prerender.py [--api https://d2zs12dmk7373h.cloudfront.net]

Data comes from the public API (read-only). Run it after the live incident is analyzed,
then build and deploy as usual.
"""
import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from html import escape
from pathlib import Path

INDEX = Path(__file__).resolve().parent.parent / "frontend" / "index.html"
START, END = "<!-- PRERENDER:START -->", "<!-- PRERENDER:END -->"
SOURCE = {"LIVE_DEMO": "Live demo", "CAPTURED_DEMO": "Captured demo", "SEEDED_DEMO": "Seeded demo (fictional)"}
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
    featured_row = next((r for r in rows if r["source_type"] == "LIVE_DEMO" and r.get("best_match")), None)
    e = escape
    parts = ['''<section class="intro">
      <h1>Have we seen this before?</h1>
      <p>Monitoring tells you something is wrong. Incident Memory reconstructs each AWS incident from CloudWatch and
      CloudTrail evidence, stores it as a structured memory, and compares new incidents with what happened last time.</p>
      <p class="differentiator"><b>Cloud monitoring helps you investigate what is happening now. Incident Memory remembers
      what your team learned last time:</b> incidents are kept as long-term structured memories, and the previous
      cause, action and recovery are reused when a similar pattern returns.</p>
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
        parts.append(f'''<section class="panel">
      <h2>Featured analysis: {e(m['title'])}</h2>
      <p class="muted">{e(m['id'])} · {e(SOURCE.get(m['source_type'], m['source_type']))} · Started {e(dt(m['started_at']))} ·
      Trigger: {e(t.get('alarm_name', ''))} ({e(t.get('service', ''))} {e(t.get('metric', ''))}) · AWS evidence: CloudWatch + CloudTrail</p>
      <h3>{top['score']}% similar to {e(top['incident_id'])}: {e(top['title'])}</h3>
      <p>Previous incident: {e(dt(top.get('started_at')))}, {e(SOURCE.get(top.get('source_type'), ''))}.
      Shared pattern: <b>{e(pattern(top.get('shared_sequence', [])))}</b></p>
      <h3>Why {top['score']}% similar?</h3><ul>{why}</ul>
      <h3>What is different</h3><ul>{diff}</ul>
      <h3>What happened last time?</h3>
      <ul>
        {f"<li>After the same state, {e(nxt)}.</li>" if nxt else ""}
        {f"<li>Previous suspected cause: {e(cause['description'])} ({e(cause['confidence'])})</li>" if cause else ""}
        {f"<li>Previous action: {e(r['action'])}</li>" if r else ""}
        {f"<li>Previous outcome: {e(r['result'])}</li>" if r else ""}
        {f"<li>Recovery time: {r['time_to_recovery_min']} minutes after the alarm</li>" if r else ""}
      </ul>
      {f"<h3>Incident summary (Amazon Bedrock, grounded in the evidence below)</h3><p>{e(ai)}</p>" if ai else ""}
      <h3>Timeline (real AWS evidence)</h3><ul>{timeline}</ul>
      <p class="small faint">The similarity score is calculated from five documented factors by the application, not by AI.
      It is a historical comparison, not a prediction.</p>
    </section>''')

    items = "".join(incident_item(x) for x in rows)
    parts.append(f'''<section class="panel">
      <h2>Incident memory</h2><ul>{items}</ul>
    </section>
    <section class="panel">
      <h2>How it works</h2>
      <ul>
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
    </section>''')
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
