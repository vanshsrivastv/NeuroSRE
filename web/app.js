/* NeuroSRE console: polls the API and renders the incident flight deck. No framework, no build step. */
"use strict";

const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const NS = "http://www.w3.org/2000/svg";
const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const hhmmss = ts => new Date(ts * 1000).toTimeString().slice(0, 8);
const store = { get: (k, d) => { try { return localStorage.getItem(k) ?? d; } catch { return d; } },
                set: (k, v) => { try { localStorage.setItem(k, v); } catch { /* storage unavailable */ } } };
const svg = (tag, attrs = {}, parent) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); if (parent) parent.appendChild(e); return e; };
const ICON = {
  check: '<svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="4" aria-hidden="true"><path d="m5 12 5 5 9-10"/></svg>',
  cross: '<svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="4" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>',
  warn: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M12 9v4m0 4h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/></svg>',
  ok: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" aria-hidden="true"><path d="m5 12 5 5 9-10"/></svg>',
  replay: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/></svg>',
};

async function api(path, body) {
  const opts = body === undefined ? {} : {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)};
  const r = await fetch(path, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof data.detail === "string" ? data.detail : (data.detail?.[0]?.msg || r.statusText));
  return data;
}
function toast(msg, isErr = false) {
  const t = document.createElement("div");
  t.className = "toast" + (isErr ? " err" : ""); t.textContent = msg;
  $("#toasts").appendChild(t); setTimeout(() => t.remove(), 4200);
}

/* ---------------------------------------------------------------- theme + routing */
$("#theme").onclick = () => {
  const r = document.documentElement;
  r.dataset.theme = r.dataset.theme === "dark" ? "light" : "dark";
  store.set("nsre-theme", r.dataset.theme);
};
const VIEWS = ["incidents", "services", "policy", "runbooks", "metrics"];
function route() {
  const v = VIEWS.includes(location.hash.slice(1)) ? location.hash.slice(1) : "incidents";
  VIEWS.forEach(x => $("#v-" + x).classList.toggle("hidden", x !== v));
  $$(".top nav a").forEach(a => a.classList.toggle("on", a.dataset.view === v));
  App.view = v;
  if (v === "policy") loadPolicy();
  if (v === "runbooks") loadRunbooks();
  if (v === "metrics") loadMetrics();
}
window.addEventListener("hashchange", route);

/* ---------------------------------------------------------------- service map (topology) */
const MAP = { W: 900, H: 384, BW: 168, BH: 58,
  pos: {"api-gateway": [366, 94], "auth-service": [86, 204], "payment-service": [366, 204], "worker-queue": [646, 204],
        "redis-cache": [226, 314], "orders-db": [506, 314]} };

function createTopology(host, blastHost) {
  const root = svg("svg", {viewBox: `0 0 ${MAP.W} ${MAP.H}`, role: "img", "aria-label": "Service dependency map"});
  host.appendChild(root);
  const gE = svg("g", {}, root), gD = svg("g", {}, root), gN = svg("g", {}, root);
  const cl = svg("g", {class: "clients", transform: `translate(${366},${14})`}, gN);
  svg("rect", {width: MAP.BW, height: 38, rx: 19}, cl);
  svg("text", {x: MAP.BW / 2, y: 24, "text-anchor": "middle"}, cl).textContent = "Internet clients";
  const boxes = {}, edges = [];
  for (const [name, [x, y]] of Object.entries(MAP.pos)) {
    const g = svg("g", {class: "box", transform: `translate(${x},${y})`}, gN);
    svg("rect", {class: "ring", width: MAP.BW, height: MAP.BH, rx: 9}, g);
    svg("rect", {class: "f", width: MAP.BW, height: MAP.BH, rx: 9}, g);
    svg("rect", {class: "s", width: 4, height: MAP.BH - 18, x: 0, y: 9, rx: 2}, g);
    svg("text", {x: 14, y: 21}, g).textContent = name;
    const k = svg("text", {class: "k", x: 14, y: 36}, g), m = svg("text", {class: "m", x: 14, y: 50}, g);
    boxes[name] = {g, k, m};
  }
  const link = (from, to, sx, sy, tx, ty) => {
    const my = (sy + ty) / 2, d = `M ${sx} ${sy} C ${sx} ${my}, ${tx} ${my}, ${tx} ${ty}`;
    const path = svg("path", {class: "e", d}, gE), dots = [];
    if (!reduceMotion) for (let j = 0; j < 3; j++) {
      const c = svg("circle", {class: "dot", r: 2.6}, gD);
      svg("animateMotion", {dur: `${1.6 + (edges.length % 3) * 0.25}s`, repeatCount: "indefinite", begin: `${j * 0.55 + edges.length * 0.11}s`, path: d}, c);
      dots.push(c);
    }
    edges.push({from, to, path, dots});
  };
  const ctr = n => [MAP.pos[n][0] + MAP.BW / 2, MAP.pos[n][1]];
  link("clients", "api-gateway", 366 + MAP.BW / 2, 52, ...ctr("api-gateway"));
  let deps = [];

  function update(services, dependencies) {
    if (!deps.length && dependencies) {
      deps = dependencies;
      deps.forEach(([a, b]) => { const [ax, ay] = ctr(a), [bx, by] = ctr(b); link(a, b, ax, ay + MAP.BH, bx, by); });
    }
    const byName = Object.fromEntries(services.map(s => [s.name, s]));
    const failing = new Set(services.filter(s => s.status !== "healthy").map(s => s.name));
    const impacted = new Set(deps.filter(([a, b]) => failing.has(b) && !failing.has(a)).map(([a]) => a));
    for (const [name, b] of Object.entries(boxes)) {
      const s = byName[name]; if (!s) continue;
      b.g.setAttribute("class", "box" + (failing.has(name) ? " hot" : impacted.has(name) ? " warm" : ""));
      b.k.textContent = `${s.kind} · ×${s.replicas}${s.version !== "v2.4.0" ? " · " + s.version : ""}`;
      b.m.textContent = `${Math.round(s.latency_ms)} ms · ${s.error_rate.toFixed(1)}% err`;
    }
    for (const e of edges) {
      const hot = failing.has(e.to), warm = e.from === "clients" && (failing.has(e.to) || impacted.has(e.to));
      e.path.setAttribute("class", "e" + (hot ? " hot" : warm ? " warm" : ""));
      e.dots.forEach((d, i) => d.setAttribute("class", "dot" + (hot && i < 2 ? " err" : "")));
    }
    if (blastHost) {
      const ok = services.length - failing.size - impacted.size;
      blastHost.innerHTML = failing.size
        ? `<div><b>Failing</b><span class="x">${[...failing].join(", ")}</span></div>
           <div><b>Upstream impact</b>${impacted.size ? `<span class="y">${[...impacted].join(", ")}</span> <span class="muted">(calls a failing service)</span>` : '<span class="muted">none</span>'}</div>
           <div><b>Unaffected</b>${ok} of ${services.length} services</div>`
        : `<div><b>Blast radius</b>None. All ${services.length} services are healthy.</div>`;
    }
  }
  return {update};
}
const LEGEND = '<span><i style="background:var(--ok)"></i>healthy</span><span><i style="background:var(--warn)"></i>impacted</span><span><i style="background:var(--crit)"></i>failing</span><span><i style="background:var(--accent);border-radius:50%"></i>requests</span>';
$("#legend2").innerHTML = LEGEND;

/* ---------------------------------------------------------------- agent pipeline graph */
const PIPE = ["Monitor", "Triage", "Diagnosis", "Evidence gate", "Planner", "Safety guard", "Approval", "Executor", "Verifier", "Reporter"];
const P = { W: 76, H: 36, Y: 62, X: i => 6 + i * 86 };
P.C = i => P.X(i) + P.W / 2;

function pipelineState(evs, status) {
  const count = a => evs.filter(e => e.agent === a).length, has = a => count(a) > 0;
  const escEv = evs.find(e => e.agent === "Escalation");
  const st = {nodes: Array(PIPE.length).fill(""), edges: Array(PIPE.length - 1).fill(false), retry: count("Diagnosis") > 1,
              bypass: false, esc: !!escEv, exit: null};
  const mark = (i, c) => { st.nodes[i] = c; };
  if (has("Monitor")) mark(0, "done");
  if (has("Triage")) mark(1, "done");
  if (has("Diagnosis")) mark(2, "done");
  const gateFail = evs.some(e => e.agent === "Evidence Gate" && /^Not safe/.test(e.summary));
  const gateWait = evs.some(e => e.agent === "Evidence Gate" && /^Weak/.test(e.summary));
  if (gateFail) { mark(3, "esc lit"); st.exit = 3; } else if (has("Planner")) mark(3, "done"); else if (gateWait) mark(3, "now");
  if (has("Planner")) mark(4, "done");
  if (has("Safety Guard")) mark(5, "done");
  const approval = evs.find(e => e.agent === "Human Approval");
  if (approval) mark(6, /rejected/.test(approval.summary) ? "esc lit" : "done");
  else if (has("Executor")) { mark(6, "skip"); st.bypass = true; }
  if (has("Executor")) mark(7, "done");
  if (has("Verifier")) mark(8, "done");
  if (has("Reporter")) mark(9, status === "resolved" ? "ok" : "done");
  if (escEv) {
    const r = escEv.summary;
    st.exit = /blocked/.test(r) ? 5 : /rejected/.test(r) ? 6 : /still unhealthy/.test(r) ? 8 : 3;
  }
  if (status === "awaiting_approval") mark(6, "now");
  else if (status === "investigating" && !escEv) {
    const last = st.nodes.reduce((m, c, i) => (c && c !== "skip" ? i : m), -1);
    if (last + 1 < PIPE.length && !st.nodes[last + 1]) mark(last + 1, "now");
  }
  for (let i = 0; i < PIPE.length - 1; i++) {
    const a = st.nodes[i], b = st.nodes[i + 1];
    st.edges[i] = !!a && a !== "skip" && !!b && b !== "skip" && !/esc/.test(a);
  }
  return st;
}

function drawPipeline(host, st) {
  host.innerHTML = "";
  const root = svg("svg", {viewBox: "0 0 860 172", role: "img", "aria-label": "Agent pipeline for this incident"}, host);
  const defs = svg("defs", {}, root);
  const mk = svg("marker", {id: "ah", viewBox: "0 0 8 8", refX: 7, refY: 4, markerWidth: 6, markerHeight: 6, orient: "auto"}, defs);
  svg("path", {d: "M0 0 8 4 0 8z", fill: "context-stroke"}, mk);
  const lbl = (x, y, t, bad) => { svg("text", {class: "lbl" + (bad ? " bad" : ""), x, y, "text-anchor": "middle"}, root).textContent = t; };
  svg("path", {class: "edge alt" + (st.retry ? " done" : ""), d: `M ${P.C(8)} ${P.Y} C ${P.C(8)} 4, ${P.C(2)} 4, ${P.C(2)} ${P.Y - 1}`, "marker-end": "url(#ah)"}, root);
  lbl(P.C(5), 15, "not fixed: retry diagnosis with feedback (max 3)");
  svg("path", {class: "edge alt" + (st.bypass ? " done" : ""), d: `M ${P.C(5)} ${P.Y} C ${P.C(5)} 30, ${P.C(7)} 30, ${P.C(7)} ${P.Y - 1}`, "marker-end": "url(#ah)"}, root);
  lbl(P.C(6), 40, "low / medium risk");
  const EX = 410, EW = 112, EY = 136;
  [[3, EX, "conflict"], [5, EX + 40, "blocked"], [6, EX + EW - 30, "rejected"], [8, EX + EW, "3 tries"]].forEach(([i, tx, t]) => {
    svg("path", {class: "edge bad" + (st.exit === i ? " done" : ""), d: `M ${P.C(i)} ${P.Y + P.H} C ${P.C(i)} ${EY + 4}, ${tx} ${EY - 18}, ${tx} ${EY}`}, root);
    lbl(P.C(i) + (i < 5 ? -26 : 26), P.Y + P.H + 22, t, true);
  });
  const eg = svg("g", {class: "node esc" + (st.esc ? " lit" : ""), transform: `translate(${EX},${EY})`}, root);
  svg("rect", {width: EW, height: 26, rx: 7}, eg);
  svg("text", {x: EW / 2, y: 17, "text-anchor": "middle"}, eg).textContent = "Escalate to human";
  for (let i = 0; i < PIPE.length - 1; i++)
    svg("path", {class: "edge" + (st.edges[i] ? " done" : ""), d: `M ${P.X(i) + P.W} ${P.Y + P.H / 2} L ${P.X(i + 1) - 2} ${P.Y + P.H / 2}`, "marker-end": "url(#ah)"}, root);
  PIPE.forEach((name, i) => {
    const g = svg("g", {class: "node " + st.nodes[i], transform: `translate(${P.X(i)},${P.Y})`}, root);
    svg("rect", {width: P.W, height: P.H, rx: 8}, g);
    svg("text", {x: P.W / 2, y: 22, "text-anchor": "middle"}, g).textContent = name;
  });
}

/* ---------------------------------------------------------------- incident story */
const App = { view: "incidents", data: null, detail: null, selected: null, pinned: false, filter: "all",
              logSeq: 0, faults: [], replaying: false, storySig: "", topoSmall: null, topoBig: null };

function modelTag(e) {
  if (e.mode === "llm") return `<em>${esc((e.detail?.model || "LLM").replace(/^openai\//, ""))}${e.seconds ? " · " + e.seconds + " s" : ""}</em>`;
  if (e.mode === "rules") return '<em class="rules">rules fallback</em>';
  return "";
}
function feedClass(e) {
  if (e.agent === "Evidence Gate") return /^Weak/.test(e.summary) ? "w" : "bad";
  if (e.agent === "Escalation") return "bad";
  if (e.agent === "Safety Guard") return /BLOCKED/.test(e.summary) ? "bad" : /HIGH/.test(e.summary) ? "w" : "";
  if (e.agent === "Human Approval") return /rejected/.test(e.summary) ? "bad" : "ok";
  if (e.agent === "Verifier") return /healthy again/.test(e.summary) ? "ok" : "w";
  if (e.agent === "Reporter") return /resolved/.test(e.summary) ? "ok" : "";
  if (e.agent === "Executor" && /Refused|stale/.test(e.summary)) return "w";
  return "";
}

function gateHTML(d) {
  const tri = d.triage, diag = d.diagnosis, hits = d.retrieved || [];
  if (!tri || !diag) return `<div class="gate"><div class="sig"><div class="k"><span class="tick wait"></span>Waiting for diagnosis</div></div></div>`;
  const failed = d.timeline.find(e => e.agent === "Evidence Gate" && /^Not safe/.test(e.summary));
  const passed = !failed && d.timeline.some(e => e.agent === "Planner");
  const rb = d.runbook, top = hits[0], second = hits[1];
  const okTri = tri.incident_type !== "unknown";
  const okDiag = !!rb && rb.services.includes(d.service);
  const okRet = !!rb && !!top && (top.runbook_id === rb.id || (hits.find(h => h.runbook_id === rb.id)?.score ?? -1) >= top.score - 0.03);
  const t = ok => `<span class="tick ${passed ? "" : ok ? "" : "no"}">${passed || ok ? ICON.check : ICON.cross}</span>`;
  const mode = x => x?.mode === "llm" ? "LLM" : "rules";
  return `<div class="gate">
    <div class="sig"><div class="k">${t(okTri)}Triage (${mode(tri)})</div><div class="v">${esc(tri.incident_type.replace(/_/g, " "))}<small>${esc(tri.severity)} · ${esc(tri.service)}</small></div></div>
    <div class="sig"><div class="k">${t(okDiag)}Diagnosis (${mode(diag)})</div><div class="v">${rb ? esc(rb.id) : "no runbook"}<small>${rb ? "applies to " + esc(rb.services.join(", ")) : "nothing matched"}</small></div></div>
    <div class="sig"><div class="k">${t(okRet)}Retrieval (raw logs only)</div><div class="v">${top ? esc(top.runbook_id) + " · " + top.score.toFixed(2) : "-"}<small>${second ? "next " + esc(second.runbook_id) + " · " + second.score.toFixed(2) : ""}</small></div></div>
    <div class="verdict ${passed ? "" : failed ? "no" : "wait"}"><b>${passed ? "Agree" : failed ? "Escalated" : "Checking"}</b><span>${passed ? "safe to plan a fix" : failed ? "not safe to act" : "comparing signals"}</span></div>
  </div>${failed ? `<div class="gate-why">${esc(failed.summary.replace("Not safe to act automatically: ", "Why: "))}</div>` : ""}`;
}

function decisionHTML(d) {
  if (d.status !== "awaiting_approval" || !d.pending) return "";
  const who = store.get("nsre-approver", "");
  const rows = d.pending.verdicts.map(v => `<div class="cmd"><span><span class="p">$ neuroctl</span>${esc(v.action)} ${esc(v.target)}${Object.entries(v.params || {}).map(([k, x]) => ` ${esc(k)}=${esc(x)}`).join("")}</span><span class="risk ${esc(v.risk)}">${esc(v.risk.toUpperCase())}</span></div>`).join("");
  const reasons = d.pending.verdicts.map(v => `<li><code>${esc(v.action)}</code> ${esc(v.reason)}</li>`).join("");
  return `<section class="decision" aria-label="Approval required">
    <div class="h"><span class="ic">${ICON.warn}</span><div><b>Approve a high-risk change?</b><span>The Safety guard paused this plan. Nothing runs until a named engineer decides.</span></div></div>
    ${rows}<ul class="reasons">${reasons}</ul>
    <div class="act"><label for="who">Approving as</label><input id="who" value="${esc(who)}" placeholder="your name" autocomplete="name"><span class="grow"></span>
      <button class="btn no" data-decide="0">Reject and escalate</button><button class="btn go" data-decide="1">Approve and run</button></div>
  </section>`;
}

function outcomeHTML(d) {
  const rep = d.report;
  if (d.status === "resolved" && rep) {
    const acts = (rep.actions || []).map(a => `<code>${esc(a.action)}</code>`).join(" ");
    const asked = d.timeline.find(e => e.agent === "Safety Guard" && /HIGH/.test(e.summary)), answered = d.timeline.find(e => e.agent === "Human Approval");
    const wait = asked && answered ? answered.ts - asked.ts : 0;
    const split = wait > 1 ? ` <span class="muted" style="font-weight:400">(${(rep.mttr_seconds - wait).toFixed(1)} s agents + ${wait.toFixed(1)} s waiting for approval)</span>` : "";
    return `<div class="outcome ok"><span class="ic">${ICON.ok}</span><div class="grow"><b>Resolved in ${rep.mttr_seconds} s${split}</b><span>Recovery verified from live metrics, not from the executor's word. Actions: ${acts || "none"}${rep.approval ? " · " + esc(rep.approval) : ""}</span></div></div>`;
  }
  if ((d.status === "escalated" || d.status === "blocked") && rep) {
    const waiting = App.data?.quarantined.includes(d.service);
    return `<div class="outcome esc"><span class="ic">${ICON.warn}</span><div class="grow"><b>${d.status === "blocked" ? "Blocked by the Safety guard" : "Escalated to a human"}</b><span>${esc(rep.escalation_reason || "")}. ${(rep.actions || []).length ? "" : "No action was executed."}</span></div>
      ${waiting ? `<button class="btn sm" data-fix="${esc(d.service)}">Mark ${esc(d.service)} fixed</button>` : ""}</div>`;
  }
  return "";
}

function storyHeader(d) {
  const tri = d.triage, sev = d.severity || tri?.severity;
  const lede = tri?.summary || (d.signals?.length ? "Signals: " + d.signals.join("; ") : "The agents are investigating.");
  const truth = d.true_fault ? `<span class="fact truth" title="Ground truth from the simulator, shown for evaluation. The agents never see it.">injected: ${esc(d.true_fault)}</span>` : "";
  return `<div>
    <div class="crumb">${esc(d.id)} · opened ${hhmmss(d.opened)}${d.attempts ? ` · attempt ${d.attempts}` : ""}
      <span class="rp"><button class="btn sm" id="replay">${ICON.replay}Replay incident</button></span></div>
    <h1>${esc(d.title)} on ${esc(d.service)}</h1>
    <div class="facts">${sev ? `<span class="fact ${sev === "P1" ? "p1" : ""}">${esc(sev)}</span>` : ""}<span class="fact">${esc(d.service)}</span>
      ${d.runbook ? `<span class="fact">runbook ${esc(d.runbook.id)}</span>` : ""}<span class="fact">${esc((d.stage || d.status).toLowerCase())}</span>${truth}</div>
    <p class="lede">${esc(lede)}</p></div>`;
}

function feedHTML(d, upTo) {
  const evs = d.timeline.slice(0, upTo ?? d.timeline.length);
  const llm = d.timeline.filter(e => e.mode === "llm");
  return `<section class="card" aria-label="Agent activity"><div class="card-h"><h3>Agent activity</h3><span class="m">${d.timeline.length} events · ${llm.length} LLM calls · ${llm.reduce((s, e) => s + (e.seconds || 0), 0).toFixed(1)} s reasoning</span></div>
    <ol class="feed">${evs.map(e => `<li class="${feedClass(e)}"><span class="t">${hhmmss(e.ts)}</span><div><div class="who"><span>${esc(e.agent)}</span>${modelTag(e)}</div><div class="msg">${esc(e.summary)}</div></div></li>`).join("")}</ol></section>`;
}

function renderStory(force = false) {
  const host = $("#story"), d = App.detail;
  if (App.replaying) return;
  if (!d) {
    const s = App.data;
    const sig = "empty" + (s ? s.kpis.healthy : "");
    if (!force && App.storySig === sig) return;
    App.storySig = sig;
    host.innerHTML = `<div><div class="crumb">no open incidents</div><h1>All systems operational</h1>
      <p class="lede">The Monitor checks every service every 2 seconds. Inject a fault from the Chaos panel, or switch on Auto chaos, and watch the agents respond.</p></div>
      <div id="mapSlot"></div>`;
    mountMap();
    return;
  }
  const sig = [d.id, d.status, d.stage, d.timeline.length, !!d.pending, App.data?.quarantined.join()].join("|");
  if (!force && sig === App.storySig) return;
  App.storySig = sig;
  host.innerHTML = `${storyHeader(d)}${outcomeHTML(d)}
    <section class="card" aria-label="Agent pipeline"><div class="card-h"><h3>Agent pipeline</h3><span class="m">LangGraph · path taken by this incident</span></div><div class="pipe" id="pipe"></div></section>
    <section class="card" aria-label="Evidence gate"><div class="card-h"><h3>Evidence gate</h3><span class="m">acts only when independent signals agree</span></div>${gateHTML(d)}</section>
    ${decisionHTML(d)}<div id="mapSlot"></div><div id="feedSlot">${feedHTML(d)}</div>`;
  drawPipeline($("#pipe"), pipelineState(d.timeline, d.status));
  mountMap();
}

function mountMap() {
  // the small map card is created once and moved into place, so its traffic animation never restarts
  if (!App.mapCard) {
    App.mapCard = document.createElement("section");
    App.mapCard.className = "card"; App.mapCard.setAttribute("aria-label", "Service map");
    App.mapCard.innerHTML = `<div class="card-h"><h3>Service map</h3><span class="muted" style="font-size:12px">blast radius</span><span class="m legend">${LEGEND}</span></div><div class="topo"></div><div class="blast"></div>`;
    App.topoSmall = createTopology(App.mapCard.querySelector(".topo"), App.mapCard.querySelector(".blast"));
    if (App.data) App.topoSmall.update(App.data.services, App.data.dependencies);
  }
  $("#mapSlot")?.replaceWith(App.mapCard);
}

function replay() {
  const d = App.detail; if (!d) return;
  App.replaying = true;
  const n = d.timeline.length; let k = 0;
  const feedSlot = $("#feedSlot"), pipe = $("#pipe");
  const step = () => {
    const evs = d.timeline.slice(0, k);
    const status = k >= n ? d.status : "investigating";
    drawPipeline(pipe, pipelineState(evs, status));
    feedSlot.innerHTML = feedHTML(d, k);
    if (k++ >= n) { App.replaying = false; return; }
    setTimeout(step, reduceMotion ? 0 : 550);
  };
  step();
}

$("#story").addEventListener("click", async ev => {
  const b = ev.target.closest("button"); if (!b) return;
  if (b.id === "replay") return replay();
  if (b.dataset.fix) {
    try { await api(`/api/services/${encodeURIComponent(b.dataset.fix)}/fix`, {}); toast(`${b.dataset.fix} marked as fixed`); poll(); }
    catch (e) { toast(e.message, true); }
  }
  if (b.dataset.decide !== undefined) {
    const who = ($("#who")?.value || "").trim();
    if (who.length < 2) { toast("Enter your name before approving or rejecting", true); $("#who")?.focus(); return; }
    store.set("nsre-approver", who);
    b.disabled = true;
    try { await api(`/api/incidents/${App.selected}/decision`, {approve: b.dataset.decide === "1", by: who});
          toast(b.dataset.decide === "1" ? "Approved. Executing the plan." : "Rejected. Incident escalated."); poll(); }
    catch (e) { toast(e.message, true); b.disabled = false; }
  }
});
$("#story").addEventListener("input", ev => { if (ev.target.id === "who") store.set("nsre-approver", ev.target.value); });

/* ---------------------------------------------------------------- queue, services, logs */
const STATUS_TAG = {awaiting_approval: ["wait", "Needs approval"], investigating: ["run", "Investigating"], resolved: ["ok", ""],
                    escalated: ["esc", "Escalated"], blocked: ["esc", "Blocked"], error: ["esc", "Error"]};
function renderQueue(incs) {
  const f = App.filter;
  const list = incs.filter(i => f === "all" || (f === "me" && i.status === "awaiting_approval") ||
                                 (f === "resolved" && i.status === "resolved") || (f === "esc" && ["escalated", "blocked"].includes(i.status)));
  $("#qCount").textContent = `${incs.filter(i => ["investigating", "awaiting_approval"].includes(i.status)).length} open · ${incs.length} total`;
  $("#queue").innerHTML = list.length ? list.map(i => {
    const [cls, label] = STATUS_TAG[i.status] || ["gray", i.status];
    const tag = i.status === "resolved" ? `${i.mttr} s` : label;
    const detail = i.status === "resolved" ? (i.actions.join(", ") || "recovered") : i.reason || (i.stage || "").toLowerCase();
    return `<button class="q ${i.id === App.selected ? "sel" : ""}" data-id="${esc(i.id)}"><span class="rail"></span><span class="in">
      <span class="l1">${esc(i.id)} · ${hhmmss(i.opened).slice(0, 5)}<span class="tag ${cls}">${esc(tag)}</span></span>
      <span class="l2" style="display:block">${esc(i.title)}</span><span class="l3" style="display:block">${esc(i.service)}${i.severity ? " · " + esc(i.severity) : ""} · ${esc(detail)}</span></span></button>`;
  }).join("") : `<div class="empty-q">${incs.length ? "Nothing in this filter." : "No incidents yet. Inject a fault to start."}</div>`;
}
$("#queue").addEventListener("click", ev => {
  const q = ev.target.closest(".q"); if (!q) return;
  App.selected = q.dataset.id; App.pinned = true; App.storySig = ""; poll();
});
$$(".seg button").forEach(b => b.onclick = () => {
  $$(".seg button").forEach(x => x.classList.toggle("on", x === b)); App.filter = b.dataset.f; if (App.data) renderQueue(App.data.incidents);
});

const gauge = (v, hi) => `<span class="g ${hi ? "hi" : ""}">${Math.round(v)}%<span><i style="width:${Math.min(100, v)}%"></i></span></span>`;
function renderServices(services) {
  $("#svcCount").textContent = `${services.filter(s => s.status === "healthy").length} of ${services.length} healthy`;
  $("#rows").innerHTML = services.map(s => `<div class="row ${s.status !== "healthy" ? "bad" : ""}"><span class="d"></span><span class="n">${esc(s.name)}</span>
    ${gauge(s.cpu, s.cpu >= 85)}${gauge(s.memory, s.memory >= 90)}<span class="e">${s.error_rate.toFixed(1)}%</span></div>`).join("");
  if (App.view === "services") {
    $("#svcTable").innerHTML = services.map(s => {
      const ex = s.extra || {};
      const extra = [ex.connections !== undefined ? `connections ${ex.connections}/${ex.pool_size}` : "", ex.queue_depth !== undefined ? `queue ${ex.queue_depth.toLocaleString()}` : "",
                     ex.cert_days_left !== undefined ? `certificate ${ex.cert_days_left} days` : ""].filter(Boolean).join(" · ");
      const tag = s.status === "healthy" ? "ok" : "esc";
      return `<tr><td><b>${esc(s.name)}</b><div class="muted" style="font-size:12px">${esc(s.kind)}</div></td><td><span class="tag ${tag}">${esc(s.status.toUpperCase())}</span></td>
        <td class="m">${Math.round(s.cpu)}%</td><td class="m">${Math.round(s.memory)}%</td><td class="m">${Math.round(s.disk)}%</td><td class="m">${Math.round(s.latency_ms)} ms</td>
        <td class="m" style="${s.error_rate >= 10 ? "color:var(--crit);font-weight:600" : ""}">${s.error_rate.toFixed(1)}%</td><td class="m">${s.replicas}</td><td class="m">${esc(s.version)}</td><td class="m">${esc(extra)}</td></tr>`;
    }).join("");
  }
}
function renderLogs(logs) {
  const term = $("#term");
  for (const l of logs) {
    const act = l.message.startsWith("[neuroctl]"), lv = act ? "ACT" : l.level;
    const d = document.createElement("div");
    d.innerHTML = `<span class="t">${hhmmss(l.ts)}</span> <span class="${lv}">${{ERROR: "ERR", WARN: "WRN", INFO: "INF", ACT: "ACT"}[lv]}</span> <span class="s">${esc(l.service)}</span> ${esc(l.message.replace("[neuroctl] ", "neuroctl "))}`;
    term.appendChild(d);
    App.logSeq = Math.max(App.logSeq, l.seq);
  }
  while (term.children.length > 14) term.firstChild.remove();
}
function renderWaiting(list) {
  $("#waitingWrap").classList.toggle("hidden", !list.length);
  $("#waiting").innerHTML = list.map(s => `<div class="w"><span class="grow">${esc(s)}</span><button class="btn sm" data-fix="${esc(s)}">Mark fixed</button></div>`).join("");
}
$("#waiting").addEventListener("click", async ev => {
  const b = ev.target.closest("[data-fix]"); if (!b) return;
  try { await api(`/api/services/${encodeURIComponent(b.dataset.fix)}/fix`, {}); toast(`${b.dataset.fix} marked as fixed`); poll(); } catch (e) { toast(e.message, true); }
});

/* ---------------------------------------------------------------- header + kpis */
function renderHeader(s) {
  const k = s.kpis;
  $("#kHealthy").innerHTML = `${k.healthy}<small> / ${k.total}</small>`;
  $("#kBar").innerHTML = s.services.map(x => `<i class="${x.status === "healthy" ? "" : "bad"}"></i>`).join("");
  $("#kOpen").textContent = k.open; $("#kOpen").classList.toggle("crit", k.open > 0);
  $("#kOpenD").textContent = k.awaiting ? `${k.awaiting} waiting for your approval` : k.open ? "agents working" : "nothing open";
  $("#kResolved").textContent = k.resolved; $("#kEsc").textContent = k.escalated;
  $("#kMttr").innerHTML = k.mttr_median != null ? `${k.mttr_median.toFixed(1)}<small> s</small>` : "-";
  const nav = $("#navOpen"); nav.textContent = k.open; nav.classList.toggle("hidden", !k.open);
  const m = $("#model");
  m.textContent = s.llm.enabled ? s.llm.label.replace("openai/", "") : "rules only (offline)";
  m.classList.toggle("fallback", !s.llm.enabled || s.llm.failures > 0);
  m.title = s.llm.enabled ? `${s.llm.calls} LLM calls · ${s.llm.backup_used} answered by the backup model · ${s.llm.failures} fell back to rules` : "No API key: agents use rule-based fallbacks";
  $("#clock").textContent = hhmmss(s.now);
  $("#sAuto").checked = s.settings.auto; $("#sHard").checked = s.settings.hard;
}

/* ---------------------------------------------------------------- chaos controls */
async function initChaos() {
  App.faults = await api("/api/faults");
  const known = App.faults.filter(f => f.known), unknown = App.faults.filter(f => !f.known);
  $("#fFault").innerHTML = `<optgroup label="Has a runbook">${known.map(f => `<option value="${f.id}">${esc(f.title)}</option>`).join("")}</optgroup>
    <optgroup label="No runbook (should escalate)">${unknown.map(f => `<option value="${f.id}">${esc(f.title.replace(" (no runbook)", ""))}</option>`).join("")}</optgroup>`;
  const targets = () => { const f = App.faults.find(x => x.id === $("#fFault").value); $("#fTarget").innerHTML = f.targets.map(t => `<option>${esc(t)}</option>`).join(""); };
  $("#fFault").onchange = targets; targets();
}
const injected = r => { toast(`Injected: ${r.title} on ${r.service}`); App.pinned = false; poll(); };
$("#bInject").onclick = () => api("/api/inject", {fault: $("#fFault").value, service: $("#fTarget").value}).then(injected).catch(e => toast(e.message, true));
$("#bRandom").onclick = () => api("/api/inject", {}).then(injected).catch(e => toast(e.message, true));
$("#bAttack").onclick = () => api("/api/inject", {fault: "bad_deployment", service: "payment-service", injection: true}).then(injected).catch(e => toast(e.message, true));
$("#sAuto").onchange = e => api("/api/settings", {auto: e.target.checked}).then(() => toast(e.target.checked ? "Auto chaos on: a random fault whenever the cloud is idle" : "Auto chaos off"));
$("#sHard").onchange = e => api("/api/settings", {hard: e.target.checked}).then(() => toast(e.target.checked ? "Hard mode on: unseen log wording and misleading lines" : "Hard mode off"));

/* ---------------------------------------------------------------- polling */
let failures = 0;
async function poll() {
  try {
    const s = await api(`/api/state?since=${App.logSeq}`);
    App.data = s; failures = 0;
    $("#live").classList.remove("bad"); $("#liveText").textContent = "live · sim-cluster";
    renderHeader(s); renderServices(s.services); renderLogs(s.logs); renderWaiting(s.quarantined);
    // choose which incident to show: the user's pick, otherwise the newest open one
    const open = s.incidents.find(i => ["investigating", "awaiting_approval"].includes(i.status));
    if (!App.pinned && open && open.id !== App.selected) App.selected = open.id;
    if (!App.selected && s.incidents.length) App.selected = s.incidents[0].id;
    renderQueue(s.incidents);
    App.detail = App.selected ? await api(`/api/incidents/${App.selected}`).catch(() => null) : null;
    if (App.view === "incidents") renderStory();
    App.topoSmall?.update(s.services, s.dependencies);
    if (App.view === "services") { if (!App.topoBig) App.topoBig = createTopology($("#topoBig"), $("#blastBig")); App.topoBig.update(s.services, s.dependencies); }
  } catch (e) {
    if (++failures >= 2) { $("#live").classList.add("bad"); $("#liveText").textContent = "offline: retrying"; }
  }
}

/* ---------------------------------------------------------------- other views */
async function loadPolicy() {
  if ($("#policy").children.length) return;
  const rows = await api("/api/policy");
  $("#policy").innerHTML = rows.map(r => `<tr><td class="m">${esc(r.action)}</td><td><span class="tag ${r.risk}">${r.risk.toUpperCase()}</span></td><td>${esc(r.description)}</td>
    <td class="m">${Object.entries(r.limits).map(([k, [a, b]]) => `${esc(k)} ${a}-${b}`).join(", ") || "-"}</td><td>${esc(r.applies_to.join(", ") || "any service")}</td></tr>`).join("");
}
$("#bRed").onclick = async () => {
  const rows = await api("/api/redteam", {});
  $("#red").innerHTML = rows.map(r => `<tr><td>${esc(r.attack)}</td><td class="m">${esc(r.command)}</td><td><span class="tag ${r.verdict === "BLOCKED" ? "blocked" : "ok"}">${esc(r.verdict)}</span></td><td>${esc(r.reason)}</td></tr>`).join("");
  toast(`${rows.filter(r => r.verdict === "BLOCKED").length} of ${rows.length} unsafe plans blocked`);
};

function md(text) {
  const out = []; let inCode = false, list = false;
  for (const line of text.split("\n")) {
    if (line.startsWith("```")) { out.push(inCode ? "</pre>" : "<pre>"); inCode = !inCode; continue; }
    if (inCode) { out.push(esc(line)); continue; }
    if (/^\s*([-*]|\d+\.)\s/.test(line)) { if (!list) { out.push("<ul>"); list = true; } out.push(`<li>${esc(line.replace(/^\s*([-*]|\d+\.)\s/, ""))}</li>`); continue; }
    if (list) { out.push("</ul>"); list = false; }
    if (line.startsWith("## ")) out.push(`<h2>${esc(line.slice(3))}</h2>`);
    else if (line.startsWith("# ")) out.push(`<h1>${esc(line.slice(2))}</h1>`);
    else if (line.trim()) out.push(`<p>${esc(line)}</p>`);
  }
  if (list) out.push("</ul>");
  return out.join("\n").replace(/<pre>\n/g, "<pre>");
}
async function openRunbook(id) {
  const rb = await api(`/api/runbooks/${encodeURIComponent(id)}`);
  $("#kbText").innerHTML = `<p class="muted mono" style="margin-top:14px">${esc(rb.id)} · ${esc(rb.severity)} · applies to ${esc(rb.services.join(", "))}</p>` + md(rb.text);
}
async function loadRunbooks() {
  if ($("#kbList").children.length) return;
  const list = await api("/api/runbooks");
  $("#kbSub").textContent = `The knowledge base the Diagnosis agent searches: ${list.length} runbooks, embedded with all-MiniLM-L6-v2 in ${App.data?.kb.backend || "ChromaDB"}.`;
  $("#kbList").innerHTML = list.map(r => `<button class="hit" data-rb="${esc(r.id)}"><span class="sc">${esc(r.severity)}</span><b>${esc(r.id)}</b> ${esc(r.title)}<div class="muted mono" style="font-size:12px">${esc(r.commands.join(" ; "))}</div></button>`).join("");
}
$("#v-runbooks").addEventListener("click", ev => { const b = ev.target.closest("[data-rb]"); if (b) openRunbook(b.dataset.rb); });
$("#kbForm").onsubmit = async ev => {
  ev.preventDefault();
  const q = $("#kbQ").value.trim(); if (!q) return;
  const hits = await api(`/api/search?q=${encodeURIComponent(q)}&k=3`);
  $("#kbHits").innerHTML = hits.map(h => `<button class="hit" data-rb="${esc(h.runbook_id)}"><span class="sc">similarity ${h.score.toFixed(2)}</span><b>${esc(h.runbook_id)}</b> ${esc(h.title)}
    <div class="muted" style="font-size:12px">best section: ${esc(h.section)}</div><div class="bar"><i style="width:${Math.max(4, h.score * 100)}%"></i></div></button>`).join("");
  if (hits[0]) openRunbook(hits[0].runbook_id);
};

async function loadMetrics() {
  const m = await api("/api/metrics");
  const pct = (a, b) => b ? Math.round(100 * a / b) + "%" : "-";
  const med = m.mttr.length ? [...m.mttr].sort((a, b) => a - b)[Math.floor(m.mttr.length / 2)].toFixed(1) + " s" : "-";
  const types = Object.entries(m.by_type).sort((a, b) => b[1].runs - a[1].runs);
  const bars = m.mttr.slice(0, 30).reverse(), max = Math.max(5, ...bars);
  const bw = 900 / Math.max(bars.length, 1);
  $("#metricsPage").innerHTML = `<h2 class="title">Metrics</h2><p class="sub">All incidents stored in the audit database (${m.total}). Benchmarks are produced by <code>scripts/evaluate.py</code>.</p>
    <div class="statgrid"><div class="stat"><div class="l">Incidents</div><div class="v num">${m.total}</div></div><div class="stat"><div class="l">Auto-resolved</div><div class="v num">${pct(m.resolved, m.total)}</div></div>
      <div class="stat"><div class="l">Escalated to a human</div><div class="v num">${m.escalated}</div></div><div class="stat"><div class="l">Median time to resolve</div><div class="v num">${med}</div></div></div>
    <div class="two"><section class="card"><div class="card-h"><h3>Time to resolve, recent incidents</h3><span class="m">seconds</span></div><div class="bars" style="padding:10px 14px">
      ${bars.length ? `<svg viewBox="0 0 900 170" preserveAspectRatio="none" role="img" aria-label="Time to resolve per incident">${bars.map((v, i) => `<rect x="${i * bw + 2}" y="${160 - v / max * 150}" width="${Math.max(2, bw - 4)}" height="${v / max * 150}" rx="2"><title>${v} s</title></rect>`).join("")}</svg>` : '<p class="muted">No resolved incidents yet.</p>'}</div></section>
      <section class="card"><div class="card-h"><h3>By fault type (ground truth)</h3></div><table class="t"><thead><tr><th>Fault</th><th>Runs</th><th>Resolved</th><th>Escalated</th><th>Triage correct</th></tr></thead>
      <tbody>${types.map(([t, v]) => `<tr><td class="m">${esc(t)}</td><td class="m">${v.runs}</td><td class="m">${v.resolved}</td><td class="m">${v.escalated}</td><td class="m">${pct(v.triage_ok, v.runs)}</td></tr>`).join("") || '<tr><td colspan="5" class="muted">No data yet.</td></tr>'}</tbody></table></section></div>
    ${m.benchmarks.map(b => `<section class="card"><div class="card-h"><h3>${esc(b.title)}</h3><span class="m mono">docs/evaluation/${esc(b.file)}</span></div><table class="t"><tbody>${b.rows.map(r => `<tr><td>${esc(r[0])}</td><td class="m">${esc(r[1] || "")}</td></tr>`).join("")}</tbody></table></section>`).join("")}
    <section class="card"><div class="card-h"><h3>Recent incidents</h3></div><table class="t"><thead><tr><th>Incident</th><th>Service</th><th>Classified</th><th>Injected</th><th>Status</th><th>Runbook</th><th>Approval</th><th>Seconds</th></tr></thead>
      <tbody>${m.recent.map(r => `<tr><td class="m">${esc(r.id)}</td><td>${esc(r.service)}</td><td class="m">${esc(r.type)}</td><td class="m">${esc(r.truth)}</td><td><span class="tag ${r.status === "resolved" ? "ok" : "esc"}">${esc(r.status)}</span></td><td class="m">${esc(r.runbook || "-")}</td><td>${esc(r.approval || "-")}</td><td class="m">${r.mttr ?? "-"}</td></tr>`).join("") || '<tr><td colspan="8" class="muted">No incidents yet.</td></tr>'}</tbody></table></section>`;
}

/* ---------------------------------------------------------------- start */
route();
initChaos().catch(e => toast("Could not load fault list: " + e.message, true));
poll();
setInterval(poll, 1000);
setInterval(() => { if (App.view === "metrics") loadMetrics().catch(() => {}); }, 6000);
