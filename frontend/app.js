"use strict";

const API = "/api";
const app = document.getElementById("app");
const tooltip = document.getElementById("tooltip");
let pollTimer = null;

// ------------------------------------------------------------------ utilities

const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function fmtTime(iso) {
  if (!iso) return "—";
  return iso.slice(11, 16);
}
function fmtDateTime(iso) {
  if (!iso) return "—";
  return `${iso.slice(0, 10)} ${iso.slice(11, 16)} UTC`;
}
function minutesBetween(a, b) {
  return Math.round((new Date(b) - new Date(a)) / 60000);
}
function fmtValue(v, unit) {
  if (v === null || v === undefined) return "—";
  if (unit === "Milliseconds") return `${Math.round(v).toLocaleString("en-US")} ms`;
  if (unit === "Percent") return `${Math.round(v)}%`;
  return Number.isInteger(v) ? v.toLocaleString("en-US") : v.toLocaleString("en-US", { maximumFractionDigits: 1 });
}
function relMin(m) {
  if (m === 0) return "0 min";
  return `${m > 0 ? "+" : "−"}${Math.abs(m)} min`;
}

const SOURCE_LABELS = {
  LIVE_DEMO: ["Live demo", "Collected from CloudWatch and CloudTrail for the controlled demo workload."],
  CAPTURED_DEMO: ["Captured demo", "Captured earlier from a controlled demo incident in this AWS environment."],
  SEEDED_DEMO: ["Seeded demo", "Fictional historical incident, seeded for demonstration. Not a real production incident."],
};
function sourceBadge(type) {
  const [label, title] = SOURCE_LABELS[type] || [type, ""];
  return `<span class="badge ${type === "LIVE_DEMO" ? "live" : ""}" title="${esc(title)}">${esc(label)}</span>`;
}
function statusBadge(status) {
  const label = { NEW: "New · not analyzed", OPEN: "Open", RESOLVED: "Resolved" }[status] || status;
  return `<span class="badge status-${esc((status || "").toLowerCase())}">${esc(label)}</span>`;
}
function evChip(id, memory) {
  if (!id) return "";
  const ev = (memory.evidence || []).find((e) => e.id === id);
  return `<button class="ev" data-ev="${esc(id)}" title="${esc(ev ? ev.summary : id)}">${esc(id)}</button>`;
}
function confidence(level) {
  const n = { HIGH: 3, MEDIUM: 2, LOW: 1 }[level] || 0;
  const bars = [1, 2, 3].map((i) => `<i class="${i <= n ? "on" : ""}"></i>`).join("");
  return `<span class="conf" title="Qualitative confidence, not a probability"><span class="bars" aria-hidden="true">${bars}</span>${esc(level)} confidence</span>`;
}

async function api(path, options = {}) {
  let res;
  try {
    res = await fetch(API + path, { ...options, headers: { accept: "application/json" } });
  } catch {
    throw new Error("The service could not be reached. Check your connection and try again.");
  }
  let body = {};
  try { body = await res.json(); } catch { /* non-JSON error page */ }
  if (res.status === 429) throw new Error("Too many requests. Please wait a few seconds and try again.");
  if (res.status === 503 || res.status === 504) throw new Error("The analysis timed out. Please try again.");
  if (!res.ok) throw new Error(body.message || `Request failed (${res.status}).`);
  return body;
}

// ------------------------------------------------------------------ routing

function route() {
  clearTimeout(pollTimer);
  const hash = location.hash || "#/";
  const m = hash.match(/^#\/incidents\/([A-Za-z0-9-]+)$/);
  if (m) return renderIncident(m[1]);
  return renderDashboard();
}
window.addEventListener("hashchange", route);
route();

// ------------------------------------------------------------------ dashboard

async function renderDashboard() {
  document.title = "Incident Memory";
  app.innerHTML = `<p class="skeleton">Loading incidents…</p>`;
  let data;
  try {
    data = await api("/incidents");
  } catch (e) {
    app.innerHTML = `<div class="notice error">${esc(e.message)}</div>`;
    return;
  }
  const rows = data.incidents;
  const live = rows.filter((r) => r.source_type === "LIVE_DEMO");
  const history = rows.filter((r) => r.source_type !== "LIVE_DEMO");

  app.innerHTML = `
    <section class="intro">
      <h1>Have we seen this before?</h1>
      <p>Monitoring tells you something is wrong. Incident Memory reconstructs each AWS incident from CloudWatch and
      CloudTrail evidence, stores it as a structured memory, and compares new incidents with what happened last time.</p>
    </section>
    ${(data.warnings || []).map((w) => `<div class="notice warn" style="margin-bottom:12px">${esc(w)}</div>`).join("")}
    <section class="panel">
      <div class="section-head">
        <h2>Current incidents</h2>
        <span class="small muted">Alarms from the demo workload in the last 14 days</span>
      </div>
      ${live.length ? incidentTable(live) : `<p class="muted">No live demo incident in the last 14 days. Historical memories are listed below.</p>`}
    </section>
    <section class="panel">
      <div class="section-head">
        <h2>Incident memory</h2>
        <span class="small muted">Resolved incidents used for historical comparison</span>
      </div>
      ${incidentTable(history)}
      <ul class="legend-list">
        ${Object.entries(SOURCE_LABELS).map(([k, [label, desc]]) => `<li><b>${esc(label)}</b> — ${esc(desc)}</li>`).join("")}
      </ul>
    </section>`;
  app.querySelectorAll("tr[data-id]").forEach((tr) =>
    tr.addEventListener("click", (ev) => {
      if (ev.target.closest("a")) return;
      location.hash = `#/incidents/${tr.dataset.id}`;
    }));
}

function incidentTable(rows) {
  return `<div class="table-wrap"><table class="dash-table">
    <thead><tr><th>Incident</th><th>Status</th><th>Started</th><th>Trigger</th><th>Highest similarity</th><th>Source</th><th></th></tr></thead>
    <tbody>${rows.map((r) => `
      <tr class="clickable" data-id="${esc(r.id)}">
        <td><div class="inc-id">${esc(r.id)}</div><div>${esc(r.title)}</div></td>
        <td>${statusBadge(r.status)}</td>
        <td class="mono">${esc(fmtDateTime(r.started_at))}</td>
        <td class="hide-sm"><span class="mono small">${esc(r.trigger?.alarm_name || "—")}</span></td>
        <td class="match-cell">${r.best_match ? `<b>${r.best_match.score}%</b> <span class="muted">· ${esc(r.best_match.id)}</span>`
          : `<span class="faint">${r.analyzed_at ? "No match ≥ 60%" : r.source_type === "LIVE_DEMO" ? "Not analyzed" : "—"}</span>`}</td>
        <td class="hide-sm">${sourceBadge(r.source_type)}</td>
        <td><a href="#/incidents/${esc(r.id)}">View Incident</a></td>
      </tr>`).join("")}
    </tbody></table></div>`;
}

// ------------------------------------------------------------------ incident

async function renderIncident(id, preloaded) {
  let m = preloaded;
  if (!m) {
    app.innerHTML = `<p class="skeleton">Loading incident…</p>`;
    try {
      m = await api(`/incidents/${encodeURIComponent(id)}`);
    } catch (e) {
      app.innerHTML = `<a class="crumb" href="#/">← All incidents</a><div class="notice error">${esc(e.message)}</div>`;
      return;
    }
  }
  document.title = `${m.id} · Incident Memory`;
  const a = m.analysis;
  const isLive = m.source_type === "LIVE_DEMO";

  app.innerHTML = `
    <a class="crumb" href="#/">← All incidents</a>
    <section class="inc-head">
      <div class="row">${statusBadge(m.status)} ${sourceBadge(m.source_type)} <span class="inc-id muted">${esc(m.id)}</span></div>
      <h1>${esc(m.title)}</h1>
      <div class="meta">
        <span>Started <b class="mono">${esc(fmtDateTime(m.started_at))}</b></span>
        <span>Ended <b class="mono">${m.ended_at ? esc(fmtDateTime(m.ended_at)) : "not yet"}</b></span>
        <span>Region <b>${esc(m.region)}</b></span>
        ${a?.analyzed_at ? `<span>Analyzed <b class="mono">${esc(fmtDateTime(a.analyzed_at))}</b></span>` : ""}
      </div>
    </section>
    ${triggerPanel(m)}
    ${isLive ? analyzeBar(m) : ""}
    <div id="results">${isLive && !a ? "" : resultsHTML(m)}</div>`;

  bindCommon(m);
  const btn = document.getElementById("analyze-btn");
  if (btn) btn.addEventListener("click", () => runAnalysis(m.id));
  if (a?.ai_status === "PENDING") pollAI(m.id, 0);
}

function triggerPanel(m) {
  const t = m.trigger || {};
  return `<section class="panel">
    <div class="section-head"><h2>Trigger</h2></div>
    <div class="trigger">
      <div class="kv"><div class="k">Alarm</div><div class="v mono">${esc(t.alarm_name || "—")}</div></div>
      <div class="kv"><div class="k">Category</div><div class="v">${esc(t.alarm_category || "—")}</div></div>
      <div class="kv"><div class="k">Service · metric</div><div class="v">${esc([t.service, t.metric].filter(Boolean).join(" · ") || "—")}</div></div>
      <div class="kv"><div class="k">Observed / threshold</div><div class="v">${esc(fmtValue(t.value, t.unit))} / ${esc(fmtValue(t.threshold, t.unit))}</div></div>
      <div class="kv"><div class="k">Alarm time</div><div class="v mono">${esc(fmtDateTime(t.ts))}</div></div>
    </div>
  </section>`;
}

function analyzeBar(m) {
  const a = m.analysis;
  return `<section class="panel analyze-bar">
    <div>
      <h2>${a ? "Analysis" : "This incident has not been analyzed yet"}</h2>
      <div class="small muted">Collects CloudWatch alarms and metrics and CloudTrail changes from ${a ? esc(fmtTime(a.window.start)) + "–" + esc(fmtTime(a.window.end)) + " UTC" : "30 minutes before to 15 minutes after the alarm"}, then compares the pattern with ${a ? a.compared_count : "all"} resolved incidents.</div>
    </div>
    <button class="btn ${a ? "" : "primary"}" id="analyze-btn">${a ? "Re-run analysis" : "Analyze Incident"}</button>
  </section>`;
}

async function runAnalysis(id) {
  const btn = document.getElementById("analyze-btn");
  const results = document.getElementById("results");
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span> Analyzing…`;
  results.innerHTML = `<section class="panel"><ul class="progress-steps">
    <li>Collecting CloudWatch alarms and metrics…</li>
    <li>Collecting CloudTrail change events…</li>
    <li>Reconstructing the timeline and comparing with incident memory…</li></ul></section>`;
  try {
    const m = await api(`/incidents/${encodeURIComponent(id)}/analyze`, { method: "POST" });
    renderIncident(id, m);
  } catch (e) {
    btn.disabled = false;
    btn.textContent = "Analyze Incident";
    results.innerHTML = `<div class="notice error">Analysis failed: ${esc(e.message)}</div>`;
  }
}

function pollAI(id, attempt) {
  pollTimer = setTimeout(async () => {
    try {
      const m = await api(`/incidents/${encodeURIComponent(id)}`);
      if (m.analysis?.ai_status === "PENDING" && attempt < 40) return pollAI(id, attempt + 1);
      if (location.hash === `#/incidents/${id}`) renderIncident(id, m);
    } catch {
      if (attempt < 40) pollAI(id, attempt + 1);
    }
  }, 3000);
}

// ------------------------------------------------------------------ results

function resultsHTML(m) {
  const a = m.analysis;
  const isLive = m.source_type === "LIVE_DEMO";
  const matches = a?.similar || [];
  const explanation = pickExplanation(m);
  return `
    ${isLive ? sourcesNotice(a) : ""}
    ${isLive ? heroHTML(m, matches, a) : ""}
    <section class="panel">
      <div class="section-head"><h2>Incident Summary</h2>${explanation.badge}</div>
      <p style="margin:0">${esc(explanation.summary || "No summary available.")}</p>
      ${explanation.note ? `<p class="small muted" style="margin:8px 0 0">${esc(explanation.note)}</p>` : ""}
    </section>
    ${isLive && matches[0] ? compareChartPanel(m, matches[0]) : ""}
    <div class="grid-2 section" style="margin-top:16px">
      <section class="panel" style="margin:0">${timelineHTML(m)}</section>
      <section class="panel" style="margin:0">${causesHTML(m, explanation)}</section>
    </div>
    <section class="panel">${signalsHTML(m)}</section>
    ${isLive ? `<section class="panel">${similarHTML(m, matches, a)}</section>` : ""}
    <section class="panel">${resolutionHTML(m, matches)}</section>
    <section class="panel">${evidenceHTML(m)}</section>`;
}

function sourcesNotice(a) {
  const labels = { cloudwatch_alarms: "CloudWatch alarms", cloudwatch_metrics: "CloudWatch metrics", cloudtrail: "CloudTrail" };
  const failed = Object.entries(a.sources).filter(([, v]) => v !== "ok").map(([k]) => labels[k] || k);
  if (!failed.length) return "";
  return `<div class="notice warn" style="margin-top:16px">Partial evidence: ${esc(failed.join(", "))} could not be read.
    Conclusions that depend on this data are omitted, and affected similarity factors are excluded from the score.</div>`;
}

function heroHTML(m, matches, a) {
  if (!matches.length) {
    const near = a.best_below_threshold;
    return `<section class="hero none" style="margin-top:16px">
      <h2>No sufficiently similar historical incident was found.</h2>
      <div class="muted">Compared with ${a.compared_count} resolved incidents.${near ? ` Closest: ${esc(near.incident_id)} at ${near.score}%, below the 60% threshold.` : ""}</div>
    </section>`;
  }
  const top = matches[0];
  const next = top.next_events || [];
  const nextText = next.length
    ? next.slice(0, 2).map((e) => `${esc(e.description)} <b>${e.minutes_after_state} minutes</b> after the ${esc(e.after_description)}`).join("; ")
    : "";
  return `<section class="hero" style="margin-top:16px">
    <div class="headline">
      <span class="score">${top.score}%</span>
      <span>similar to <a href="#/incidents/${esc(top.incident_id)}"><b>${esc(top.incident_id)}</b></a> — ${esc(top.title)}
        <span class="faint small">· ${esc(fmtDateTime(top.started_at))}</span></span>
    </div>
    <div>
      <h3 style="margin-bottom:6px">Why ${top.score}% similar?</h3>
      ${whyList(top.breakdown)}
    </div>
    ${nextText ? `<div class="next">Last time: in ${esc(top.incident_id)}, ${nextText}.</div>` : ""}
    ${top.resolution ? `<div class="muted">Previously resolved by: ${esc(top.resolution.action)} (recovered ${top.resolution.time_to_recovery_min} min after the alarm)</div>` : ""}
    <div class="small faint">Historical comparison, not a prediction. The score is calculated from five documented factors, not by AI.</div>
  </section>`;
}

function whyList(breakdown) {
  const icon = (b) => b.omitted ? ["—", "excluded", "var(--text-3)"]
    : b.value >= 0.999 ? ["✓", "match", "var(--good)"]
    : b.value > 0 ? ["◐", "partial match", "var(--warning)"]
    : ["✗", "no match", "var(--critical)"];
  const order = [...breakdown].sort((a, b) => (b.value ?? -1) - (a.value ?? -1));
  return `<ul class="why">${order.map((b) => {
    const [sym, label, color] = icon(b);
    return `<li><span class="why-icon" style="color:${color}" title="${label}" aria-label="${label}">${sym}</span>
      <span><b>${esc(b.label)}</b> <span class="pts">${b.omitted ? "excluded" : `${b.points}/${b.weight}`}</span><br>
      <span class="muted small">${esc(b.reason)}</span></span></li>`;
  }).join("")}</ul>`;
}

function pickExplanation(m) {
  const a = m.analysis;
  if (!a) {
    return { summary: m.summary, causes: m.suspected_causes || [], badge: `<span class="badge">Recorded memory</span>`, insufficient: false };
  }
  if (a.ai_status === "DONE" && a.ai) {
    return {
      summary: a.ai.summary, causes: a.ai.suspected_causes, insufficient: a.ai.insufficient_evidence,
      reason: a.ai.insufficient_evidence_reason, explanations: a.ai.similarity_explanations || {},
      badge: `<span class="badge" title="Generated by Amazon Bedrock (${esc(a.ai.model_id)}) from the evidence below${a.ai_cached ? "; reused from cache for identical evidence" : ""}">AI explanation · Amazon Bedrock</span>`,
    };
  }
  const rb = a.rule_based;
  const note = a.ai_status === "PENDING" ? "Generating AI explanation…" : a.ai_error || "";
  return {
    summary: rb.summary, causes: rb.suspected_causes, insufficient: rb.insufficient_evidence, reason: rb.insufficient_evidence_reason,
    explanations: {}, note,
    badge: a.ai_status === "PENDING" ? `<span class="badge"><span class="spinner" style="width:10px;height:10px"></span> AI pending · rule-based shown</span>`
      : `<span class="badge">Rule-based analysis</span>`,
  };
}

function timelineHTML(m) {
  const items = m.timeline || [];
  const t0 = (m.trigger && m.trigger.ts) || m.started_at;
  const labels = { change: "AWS change", metric: "Metric signal", alarm: "Alarm", recovery: "Recovery", action: "Action" };
  return `<div class="section-head"><h2>Timeline</h2><span class="small muted">UTC · relative to alarm</span></div>
    ${items.length ? `<ol class="timeline">${items.map((e) => `
      <li class="${esc(e.category)}">
        <div class="t">${esc(fmtTime(e.ts))}<small>${esc(relMin(minutesBetween(t0, e.ts)))}</small></div>
        <div class="icon"><span></span></div>
        <div class="body">
          <div class="cat">${esc(labels[e.category] || e.category)} · ${esc(e.source || "")}</div>
          <div>${esc(e.description)} ${evChip(e.evidence_id, m)}</div>
        </div>
      </li>`).join("")}</ol>` : `<p class="muted">No events were found in the analysis window.</p>`}`;
}

function causesHTML(m, x) {
  const causes = x.causes || [];
  let body;
  if (!causes.length) {
    body = `<div class="notice"><b>Insufficient evidence to identify a likely cause.</b>${x.reason ? `<div class="small muted">${esc(x.reason)}</div>` : ""}</div>`;
  } else {
    body = causes.map((c) => `<div class="cause">
      ${confidence(c.confidence)}
      <div>${esc(c.description)}</div>
      ${c.reasoning ? `<div class="small muted">${esc(c.reasoning)}</div>` : ""}
      <div class="row small"><span class="faint">Supporting evidence</span> ${c.supporting_evidence.map((id) => evChip(id, m)).join(" ")}</div>
    </div>`).join("");
  }
  return `<div class="section-head"><h2>Suspected Causes</h2><span class="small muted">Correlation, not proven causation</span></div>${body}`;
}

function signalsHTML(m) {
  const signals = m.signals || [];
  const series = m.series || {};
  if (!signals.length) {
    return `<div class="section-head"><h2>Observed Signals</h2></div><p class="muted">No significant metric change was detected in the analysis window.</p>`;
  }
  return `<div class="section-head"><h2>Observed Signals</h2><span class="small muted">Sustained change ≥ 25% vs. baseline for 2+ minutes</span></div>
    <div class="table-wrap"><table class="signals"><thead><tr>
      <th>Signal</th><th>Metric</th><th>Baseline → peak</th><th>Magnitude</th><th>Window (UTC)</th><th>${Object.keys(series).length ? "Trend" : ""}</th><th>Evidence</th>
    </tr></thead><tbody>${signals.map((s) => `<tr>
      <td>${esc(s.type)}</td>
      <td><span class="mono small">${esc(s.service)} · ${esc(s.metric)}</span></td>
      <td>${esc(fmtValue(s.baseline, s.unit))} → <b>${esc(fmtValue(s.peak, s.unit))}</b></td>
      <td>${esc(s.magnitude || "")}</td>
      <td class="mono small">${esc(fmtTime(s.onset))}–${esc(fmtTime(s.until))}</td>
      <td>${series[s.metric] ? sparkline(series[s.metric], s) : ""}</td>
      <td>${(s.evidence_ids || []).map((id) => evChip(id, m)).join(" ")}</td>
    </tr>`).join("")}</tbody></table></div>`;
}

function sparkline(points, s) {
  if (!points || points.length < 2) return "";
  const w = 140, h = 32, pad = 3;
  const xs = points.map((p) => new Date(p[0]).getTime());
  const ys = points.map((p) => p[1]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  const y0 = Math.min(...ys), y1 = Math.max(...ys);
  const sx = (x) => pad + ((x - x0) / (x1 - x0 || 1)) * (w - 2 * pad);
  const sy = (y) => h - pad - ((y - y0) / (y1 - y0 || 1)) * (h - 2 * pad);
  const d = points.map((p, i) => `${i ? "L" : "M"}${sx(xs[i]).toFixed(1)},${sy(ys[i]).toFixed(1)}`).join("");
  const onset = new Date(s.onset).getTime();
  const data = esc(JSON.stringify(points.map((p) => [p[0].slice(11, 16), fmtValue(p[1], s.unit)])));
  return `<svg class="spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" data-points="${data}" role="img" aria-label="${esc(s.metric)} trend">
    <line x1="${sx(onset)}" x2="${sx(onset)}" y1="0" y2="${h}" stroke="var(--border)" stroke-dasharray="2 2"/>
    <path d="${d}" fill="none" stroke="var(--series-1)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
  </svg>`;
}

function compareChartPanel(m, top) {
  return `<section class="panel">
    <div class="section-head"><h2>Pattern comparison</h2><span class="small muted">Minutes after the preceding change (or first signal)</span></div>
    <div class="compare-chart">${compareChart(m.pattern, top)}</div>
    <div class="chart-legend">
      <span><i class="dot" style="background:var(--series-1)"></i>This incident (${esc(m.id)})</span>
      <span><i class="dot" style="background:var(--series-2)"></i>${esc(top.incident_id)}</span>
      <span><i class="dot" style="border:2px solid var(--series-2);background:transparent"></i>Happened next in ${esc(top.incident_id)}</span>
      <span><i class="dot" style="background:var(--text-3)"></i>Only in ${esc(top.incident_id)}</span>
    </div>
  </section>`;
}

function compareChart(cur, top) {
  const curEvents = Object.entries(cur.offsets_min || {}).map(([t, x]) => ({ t, x }));
  const nextTokens = new Set((top.next_events || []).map((e) => e.token));
  const histEvents = Object.entries(top.pattern?.offsets_min || {}).map(([t, x]) => ({
    t, x, next: nextTokens.has(t), onlyHist: !(t in (cur.offsets_min || {})) && !nextTokens.has(t),
  }));
  const all = [...curEvents, ...histEvents].map((e) => e.x);
  if (!all.length) return `<p class="muted">Not enough timed events to compare.</p>`;
  const maxX = Math.max(5, Math.ceil(Math.max(...all) / 5) * 5);
  const W = 900, H = 170, left = 150, right = 20;
  const sx = (x) => left + (x / maxX) * (W - left - right);
  const lane = (y, events, color, label) => {
    const sorted = [...events].sort((a, b) => a.x - b.x);
    const rightEdge = { top: -Infinity, bottom: -Infinity };  // label collision avoidance per row
    return `<text x="0" y="${y + 4}" font-size="12" fill="var(--text-2)">${esc(label)}</text>
      <line x1="${left}" x2="${W - right}" y1="${y}" y2="${y}" stroke="var(--border)"/>
      ${sorted.map((e) => {
        const x = sx(e.x);
        const name = shortToken(e.t);
        const half = name.length * 3.3;  // approx. half label width at 11px
        const side = x - half > rightEdge.top + 6 ? "top" : x - half > rightEdge.bottom + 6 ? "bottom" : "top";
        rightEdge[side] = x + half;
        const ty = side === "top" ? y - 12 : y + 26;
        const note = e.next ? " · happened next last time" : e.onlyHist ? ` · only in ${top.incident_id}` : "";
        return `<g class="cmp-pt" data-tip="${esc(`${name} · +${e.x} min${note}`)}">
          <circle cx="${x}" cy="${y}" r="10" fill="transparent"/>
          <circle cx="${x}" cy="${y}" r="5" fill="${e.next ? "var(--surface)" : e.onlyHist ? "var(--text-3)" : color}" stroke="${e.next ? color : "var(--surface)"}" stroke-width="2"/>
          <text x="${x}" y="${ty}" font-size="11" text-anchor="middle" fill="var(--text-2)">${esc(name)}</text>
        </g>`;
      }).join("")}`;
  };
  const ticks = [];
  for (let t = 0; t <= maxX; t += 5) ticks.push(t);
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" style="min-width:640px" role="img" aria-label="Event sequence comparison">
    ${ticks.map((t) => `<line x1="${sx(t)}" x2="${sx(t)}" y1="20" y2="${H - 22}" stroke="var(--border)" stroke-dasharray="2 3" opacity=".6"/>
      <text x="${sx(t)}" y="${H - 6}" font-size="11" text-anchor="middle" fill="var(--text-3)">+${t}m</text>`).join("")}
    ${lane(52, curEvents, "var(--series-1)", "This incident")}
    ${lane(112, histEvents, "var(--series-2)", top.incident_id)}
  </svg>`;
}

function shortToken(t) {
  if (t.startsWith("change:")) return `${t.slice(7)} change`;
  if (t.startsWith("alarm:")) return `${t.slice(6).split(".").pop()} alarm`;
  const [name, dir] = t.split(":");
  return `${name.split(".").pop()} ${dir === "up" ? "↑" : "↓"}`;
}

function similarHTML(m, matches, a) {
  const x = pickExplanation(m);
  const omitted = Object.entries(a.omitted_factors || {});
  const head = `<div class="section-head"><h2>Similar Incidents</h2><span class="small muted">Top ${matches.length || 0} of ${a.compared_count} resolved incidents · threshold 60%</span></div>`;
  if (!matches.length) return head + `<p class="muted">No sufficiently similar historical incident was found.</p>`;
  return head + (omitted.length ? `<div class="notice warn" style="margin-bottom:10px">Factors excluded from the score: ${omitted.map(([k, v]) => `${esc(k)} (${esc(v)})`).join("; ")}. The score is normalized over the remaining factors.</div>` : "")
    + matches.map((s) => `<div class="match">
      <div class="match-head">
        <span class="match-score">${s.score}%</span>
        <a href="#/incidents/${esc(s.incident_id)}"><b>${esc(s.incident_id)}</b></a>
        <span>${esc(s.title)}</span>
        <span class="faint small">${esc(fmtDateTime(s.started_at))}</span>
        ${sourceBadge(s.source_type)}
      </div>
      ${x.explanations && x.explanations[s.incident_id] ? `<div>${esc(x.explanations[s.incident_id])}</div>` : ""}
      <div class="factors">${s.breakdown.map((b) => `<div class="factor">
        <span>${esc(b.label)}</span>
        ${b.omitted ? `<span class="pts">excluded</span>` : `<span class="row" style="gap:6px;flex-wrap:nowrap"><span class="bar" style="width:60px"><i style="width:${(b.value * 100).toFixed(0)}%"></i></span><span class="pts">${b.points}/${b.weight}</span></span>`}
        <span class="reason small muted">${esc(b.reason)}</span>
      </div>`).join("")}</div>
    </div>`).join("");
}

function resolutionHTML(m, matches) {
  if (m.resolution) {
    return `<div class="section-head"><h2>Resolution</h2></div>${resolutionBody(m.resolution, m)}`;
  }
  const top = matches[0];
  if (!top || !top.resolution) {
    return `<div class="section-head"><h2>Previous Resolution</h2></div><p class="muted">No previous resolution is recorded for a similar incident.</p>`;
  }
  return `<div class="section-head"><h2>Previous Resolution</h2><span class="small muted">From ${esc(top.incident_id)}</span></div>
    ${resolutionBody(top.resolution)}
    ${top.suspected_causes?.length ? `<div class="small muted" style="margin-top:8px">Suspected cause recorded in ${esc(top.incident_id)}: ${esc(top.suspected_causes[0].description)}</div>` : ""}`;
}

function resolutionBody(r, m) {
  return `<div class="trigger">
    <div class="kv"><div class="k">Action taken</div><div class="v">${esc(r.action)}</div></div>
    <div class="kv"><div class="k">Result</div><div class="v">${esc(r.result)}</div></div>
    <div class="kv"><div class="k">Time to recovery</div><div class="v">${r.time_to_recovery_min} minutes from alarm</div></div>
    <div class="kv"><div class="k">Action time</div><div class="v mono">${esc(fmtDateTime(r.ts))}</div></div>
  </div>
  ${m && r.supporting_evidence?.length ? `<div class="row small" style="margin-top:8px"><span class="faint">Supporting evidence</span> ${r.supporting_evidence.map((id) => evChip(id, m)).join(" ")}</div>` : ""}`;
}

function evidenceHTML(m) {
  const ev = m.evidence || [];
  const a = m.analysis;
  const meta = a ? `<p class="small muted" style="margin:0 0 8px">Window ${esc(fmtDateTime(a.window.start))} – ${esc(fmtDateTime(a.window.end))} ·
      Sources: ${Object.entries(a.sources).map(([k, v]) => `${esc(k.replace("_", " "))} ${v === "ok" ? "✓" : "✗ unavailable"}`).join(" · ")} ·
      AI: ${esc({ DONE: "done", PENDING: "pending", UNAVAILABLE: "unavailable" }[a.ai_status] || a.ai_status)} ·
      analysis ${a.duration_ms} ms</p>` : "";
  return `<details ${m.source_type === "LIVE_DEMO" ? "" : "open"}>
    <summary>Supporting Evidence (${ev.length})</summary>
    <div style="margin-top:10px">${meta}
    <div class="table-wrap"><table class="evidence-table"><thead><tr><th>ID</th><th>Source</th><th>Time (UTC)</th><th>Evidence</th></tr></thead>
    <tbody>${ev.map((e) => `<tr id="ev-${esc(e.id)}"><td class="mono">${esc(e.id)}</td><td>${esc(e.source)}</td>
      <td class="mono small">${esc(fmtTime(e.ts || e.onset))}</td><td>${esc(e.summary)}</td></tr>`).join("")}</tbody></table></div>
    </div>
  </details>`;
}

// ------------------------------------------------------------------ interactions

function bindCommon(m) {
  app.querySelectorAll(".ev").forEach((b) => b.addEventListener("click", () => {
    const row = document.getElementById(`ev-${b.dataset.ev}`);
    if (!row) return;
    row.closest("details").open = true;
    row.scrollIntoView({ behavior: "smooth", block: "center" });
    row.classList.remove("flash");
    void row.offsetWidth;
    row.classList.add("flash");
  }));
  app.querySelectorAll("svg.spark").forEach((svg) => {
    const pts = JSON.parse(svg.dataset.points);
    svg.addEventListener("mousemove", (e) => {
      const r = svg.getBoundingClientRect();
      const i = Math.max(0, Math.min(pts.length - 1, Math.round(((e.clientX - r.left - 3) / (r.width - 6)) * (pts.length - 1))));
      showTip(`${pts[i][0]} UTC · ${pts[i][1]}`, e);
    });
    svg.addEventListener("mouseleave", hideTip);
  });
  app.querySelectorAll(".cmp-pt").forEach((g) => {
    g.addEventListener("mousemove", (e) => showTip(g.dataset.tip, e));
    g.addEventListener("mouseleave", hideTip);
  });
}
function showTip(text, e) {
  tooltip.textContent = text;
  tooltip.style.display = "block";
  tooltip.style.left = `${Math.min(e.clientX + 12, window.innerWidth - tooltip.offsetWidth - 8)}px`;
  tooltip.style.top = `${e.clientY + 14}px`;
}
function hideTip() { tooltip.style.display = "none"; }
