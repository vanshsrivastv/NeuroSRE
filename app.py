"""NeuroSRE dashboard (Streamlit).

Run:  streamlit run app.py
"""
from __future__ import annotations

import html
import time
from datetime import datetime

import pandas as pd
import streamlit as st

from neurosre import config
from neurosre.agents.safety import ALLOWLIST
from neurosre.cloud.faults import FAULTS
from neurosre.engine import Engine

st.set_page_config(page_title="NeuroSRE", page_icon="🛡️", layout="wide")

CSS = """
<style>
.block-container {padding-top: 1.4rem; padding-bottom: 1rem;}
.svc {border-radius: 10px; padding: 10px 12px; border: 1px solid rgba(128,128,128,.25); margin-bottom: 6px;}
.svc h4 {margin: 0 0 4px 0; font-size: 0.95rem;}
.svc .m {font-size: 0.78rem; opacity: .85; line-height: 1.35;}
.healthy {background: rgba(46,125,50,.10); border-left: 5px solid #2e7d32;}
.degraded {background: rgba(239,108,0,.12); border-left: 5px solid #ef6c00;}
.down {background: rgba(198,40,40,.13); border-left: 5px solid #c62828;}
.logbox {font-family: Consolas, 'Courier New', monospace; font-size: 0.74rem; line-height: 1.45;
         background: #0f172a; color: #cbd5e1; border-radius: 8px; padding: 10px; height: 470px; overflow-y: auto;}
.logbox .ERROR {color: #f87171;} .logbox .WARN {color: #fbbf24;} .logbox .INFO {color: #94a3b8;}
.logbox .svcn {color: #7dd3fc;}
.ev {border-left: 3px solid #7c3aed; padding: 4px 0 6px 10px; margin-bottom: 4px;}
.ev .a {font-weight: 700; font-size: 0.86rem;}
.ev .s {font-size: 0.82rem;}
.badge {display: inline-block; font-size: 0.68rem; padding: 1px 7px; border-radius: 9px; margin-left: 6px;
        background: rgba(124,58,237,.15); color: #7c3aed; font-weight: 600;}
.badge.rules {background: rgba(100,116,139,.18); color: #64748b;}
.badge.t {background: transparent; color: #64748b; font-weight: 400;}
.ev.Escalation, .ev.Safety-Guard.blocked {border-left-color: #c62828;}
.ev.Verifier {border-left-color: #0284c7;} .ev.Reporter {border-left-color: #2e7d32;}
.ev.Human-Approval {border-left-color: #0d9488;}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

STATUS_ICON = {"investigating": "🔄", "awaiting_approval": "✋", "resolved": "✅", "escalated": "🚨",
               "blocked": "⛔", "error": "❌"}


@st.cache_resource
def get_engine() -> Engine:
    engine = Engine()
    engine.start()
    return engine


engine = get_engine()


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.title("🛡️ NeuroSRE")
    st.caption("Agentic AI swarm for autonomous cloud self-healing")
    if engine.llm.enabled:
        st.success(f"LLM: {engine.llm.label}", icon="🧠")
    else:
        st.warning("LLM: offline rule-based mode", icon="⚙️")
        if engine.llm.last_error:
            st.caption(engine.llm.last_error)
    st.caption(f"Knowledge base: {engine.kb.backend} · {len(engine.kb.runbooks)} runbooks · "
               f"{len(engine.kb.chunks)} chunks")

    st.subheader("Chaos controls")
    fault_id = st.selectbox("Fault", list(FAULTS), format_func=lambda f: FAULTS[f].title)
    service = st.selectbox("Target service", FAULTS[fault_id].targets)
    c1, c2 = st.columns(2)
    if c1.button("💥 Inject", width="stretch"):
        f = engine.inject(fault_id, service)
        st.toast(f"Injected {fault_id} on {service}" if f else f"{service} already has an active fault")
    if c2.button("🎲 Random", width="stretch"):
        f = engine.inject()
        st.toast(f"Injected {f.spec.id} on {f.service}" if f else "All services busy")
    if st.button("🕵️ Prompt-injection attack", width="stretch",
                 help="Injects a fault AND a malicious log line telling the AI to drop the database."):
        f = engine.inject("bad_deployment", "payment-service", prompt_injection=True)
        st.toast("Attack injected on payment-service" if f else "payment-service is busy")
    engine.auto_faults = st.toggle("Auto chaos mode", value=engine.auto_faults,
                                   help="Inject a random fault whenever the cloud is idle.")
    engine.auto_interval = st.slider("Seconds between auto faults", 10, 120, int(engine.auto_interval))

    st.subheader("Engineer actions")
    for svc in sorted(engine.quarantined):
        if st.button(f"🔧 Mark {svc} fixed manually", width="stretch"):
            engine.manual_fix(svc)
            st.rerun()
    if not engine.quarantined:
        st.caption("No escalated services waiting for a human.")


# ---------------------------------------------------------------- helpers
def fmt_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%H:%M:%S")


def service_card(name: str, s: dict) -> str:
    ex = s["extra"]
    extra = ""
    if "connections" in ex:
        extra = f" · conn {ex['connections']}/{ex['pool_size']}"
    elif "queue_depth" in ex:
        extra = f" · queue {ex['queue_depth']:,}"
    elif "cert_days_left" in ex:
        extra = f" · cert {ex['cert_days_left']}d"
    return (f"<div class='svc {s['status']}'><h4>{name} <span class='badge t'>{s['status'].upper()}</span></h4>"
            f"<div class='m'>CPU {s['cpu']:.0f}% · MEM {s['memory']:.0f}% · DISK {s['disk']:.0f}%<br>"
            f"lat {s['latency_ms']:.0f}ms · err {s['error_rate']:.1f}% · ×{s['replicas']} · {s['version']}{extra}</div></div>")


def render_timeline(events: list[dict]) -> None:
    out = []
    for e in events:
        mode = e.get("mode", "system")
        badge = {"llm": "<span class='badge'>LLM</span>", "rules": "<span class='badge rules'>rules</span>"}.get(mode, "")
        secs = f"<span class='badge t'>{e['seconds']}s</span>" if e.get("seconds") else ""
        cls = e["agent"].replace(" ", "-") + (" blocked" if "BLOCKED" in e["summary"] else "")
        out.append(f"<div class='ev {cls}'><span class='a'>{html.escape(e['agent'])}</span>{badge}{secs}"
                   f"<span class='badge t'>{fmt_ts(e['ts'])}</span><div class='s'>{html.escape(e['summary'])}</div></div>")
    st.markdown("".join(out) or "<i>No agent activity yet.</i>", unsafe_allow_html=True)


def plan_table(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame([{"command": f"neuroctl {v['action']} {v['target']}" +
                          "".join(f" --{k}={x}" for k, x in (v.get("params") or {}).items()),
                          "risk": v["risk"].upper(), "policy": v["reason"]} for v in rows])


# ---------------------------------------------------------------- live view
@st.fragment(run_every=2)
def live_view():
    snap = engine.cloud.snapshot()
    reports = engine.store.all()
    incs = sorted(engine.incidents.values(), key=lambda i: i["opened"], reverse=True)
    healthy = sum(s["status"] == "healthy" for s in snap.values())
    resolved = [r for r in reports if r["status"] == "resolved"]
    mttr = sum(r["mttr_seconds"] for r in resolved) / len(resolved) if resolved else 0

    k = st.columns(5)
    k[0].metric("Healthy services", f"{healthy}/{len(snap)}")
    k[1].metric("Open incidents", sum(i["status"] in ("investigating", "awaiting_approval") for i in incs))
    k[2].metric("Auto-resolved", len(resolved))
    k[3].metric("Mean time to resolve", f"{mttr:.1f}s" if resolved else "–")
    k[4].metric("Escalated / blocked", sum(r["status"] in ("escalated", "blocked") for r in reports))

    cols = st.columns(6)
    for col, (name, s) in zip(cols, snap.items()):
        col.markdown(service_card(name, s), unsafe_allow_html=True)

    left, right = st.columns([5, 6], gap="medium")
    with left:
        st.markdown("##### 📜 Live log stream")
        lines = []
        for l in reversed(engine.cloud.recent_logs(limit=60)):
            lines.append(f"<div class='{l['level']}'>{fmt_ts(l['ts'])} <b>{l['level']:<5}</b> "
                         f"<span class='svcn'>{l['service']}</span> {html.escape(l['message'])}</div>")
        st.markdown(f"<div class='logbox'>{''.join(lines)}</div>", unsafe_allow_html=True)
    with right:
        st.markdown("##### 🤖 Agent swarm activity")
        if not incs:
            st.info("All quiet. Inject a fault from the sidebar or switch on Auto chaos mode.")
            return
        labels = [f"{STATUS_ICON.get(i['status'], '')} {i['id']} · {i['service']} · {i['status']}" for i in incs[:15]]
        pick = st.selectbox("Incident", range(len(labels)), format_func=labels.__getitem__, label_visibility="collapsed")
        inc = incs[pick]
        if inc["status"] == "awaiting_approval" and inc["pending"]:
            with st.container(border=True):
                st.markdown(f"**✋ Human approval needed: {inc['id']} on {inc['service']}**  \n"
                            f"Risk level **{inc['pending']['risk'].upper()}**. Review the plan:")
                st.dataframe(plan_table(inc["pending"]["verdicts"]), hide_index=True, width="stretch")
                a, b = st.columns(2)
                if a.button("✅ Approve & execute", key=f"ap{inc['id']}", type="primary", width="stretch"):
                    engine.decide(inc["id"], True)
                    st.rerun(scope="fragment")
                if b.button("❌ Reject & escalate", key=f"rj{inc['id']}", width="stretch"):
                    engine.decide(inc["id"], False)
                    st.rerun(scope="fragment")
        with st.container(height=420 if inc["status"] == "awaiting_approval" else 470):
            render_timeline(inc["timeline"])


# ---------------------------------------------------------------- tabs
st.markdown("## NeuroSRE · Autonomous Cloud Self-Healing")
tab_live, tab_hist, tab_safety, tab_kb, tab_metrics = st.tabs(
    ["🟢 Live operations", "📁 Incident history", "🛡️ Safety Guard", "📚 Knowledge base (RAG)", "📊 Metrics"])

with tab_live:
    live_view()

with tab_hist:
    reports = engine.store.all()
    if not reports:
        st.info("No incidents closed yet.")
    else:
        df = pd.DataFrame([{"id": r["incident_id"], "time": fmt_ts(r["detected_at"]), "service": r["service"],
                            "classified as": r["incident_type"], "actual fault": r["true_fault"],
                            "runbook": r["runbook_id"], "risk": r["risk"], "attempts": r["attempts"],
                            "status": r["status"], "MTTR (s)": r["mttr_seconds"], "engine": r["mode"]} for r in reports])
        st.dataframe(df, hide_index=True, width="stretch")
        rid = st.selectbox("Open report", [r["incident_id"] for r in reports])
        r = next(x for x in reports if x["incident_id"] == rid)
        c1, c2 = st.columns([3, 2])
        with c1:
            st.markdown(f"**{r['incident_id']} · {r['service']} · {r['status'].upper()}**  \n{r['summary']}")
            st.markdown(f"**Root cause ({r['runbook_id']}):** {r['root_cause']}")
            if r["escalation_reason"]:
                st.error(f"Escalated: {r['escalation_reason']}")
            render_timeline(r["timeline"])
        with c2:
            st.markdown("**Commands executed**")
            st.dataframe(pd.DataFrame([{"command": f"{a['action']} {a['target']} {a['params'] or ''}",
                                        "result": a["message"]} for a in r["actions"]]) if r["actions"] else
                         pd.DataFrame(), hide_index=True, width="stretch")
            st.markdown("**Runbooks retrieved (RAG)**")
            st.dataframe(pd.DataFrame([{"runbook": h["runbook_id"], "title": h["title"], "score": h["score"]}
                                       for h in r["retrieved"]]), hide_index=True, width="stretch")

with tab_safety:
    st.markdown("Every command proposed by the AI passes through the **Safety Guard** before touching the "
                "infrastructure. Low/medium-risk actions run automatically, high-risk ones need a human, and "
                "anything not on the allow-list is blocked.")
    st.dataframe(pd.DataFrame([{"action": a, "risk": p.risk.upper(), "description": p.description,
                                "limits": ", ".join(f"{k} {lo}-{hi}" for k, (lo, hi) in (p.params or {}).items()),
                                "applies to": ", ".join(p.kinds or ["any service"])} for a, p in ALLOWLIST.items()]),
                 hide_index=True, width="stretch")
    if st.button("🧪 Run red-team test against the Safety Guard"):
        rt = pd.DataFrame(engine.red_team())
        st.dataframe(rt, hide_index=True, width="stretch")
        st.success(f"{(rt['verdict'] == 'BLOCKED').sum()}/{len(rt)} unsafe plans blocked")

with tab_kb:
    q = st.text_input("Search the runbook knowledge base", "connection refused redis cache down")
    if q:
        for h in engine.kb.search(q, k=3):
            with st.expander(f"{h.runbook_id} · {h.title} · similarity {h.score}"):
                st.caption(f"best matching section: {h.section}")
                st.markdown(engine.kb.get(h.runbook_id).text)
    st.dataframe(pd.DataFrame([{"id": rb.id, "title": rb.title, "incident type": rb.incident_type,
                                "severity": rb.severity, "commands": "; ".join(rb.commands)}
                               for rb in engine.kb.runbooks.values()]), hide_index=True, width="stretch")

with tab_metrics:
    reports = engine.store.all()
    if not reports:
        st.info("Metrics appear after the first incident closes. Run `python scripts/evaluate.py` for a full benchmark.")
    else:
        df = pd.DataFrame(reports)
        res = df[df.status == "resolved"]
        labelled = df[df.true_fault.notna()]
        m = st.columns(4)
        m[0].metric("Incidents", len(df))
        m[1].metric("Auto-resolution rate", f"{len(res) / len(df):.0%}")
        m[2].metric("Triage accuracy", f"{(labelled.incident_type == labelled.true_fault).mean():.0%}"
                    if len(labelled) else "–")
        m[3].metric("Mean attempts", f"{df.attempts.mean():.2f}")
        a, b = st.columns(2)
        a.markdown("**Incidents by fault type**")
        a.bar_chart(df.groupby("true_fault").size())
        b.markdown("**Time to resolve (s) per incident**")
        if len(res):
            b.bar_chart(res.set_index("incident_id")["mttr_seconds"])
