"""HTTP API and static web console for NeuroSRE.

Run:  python -m neurosre.api            (http://127.0.0.1:8000)
"""
from __future__ import annotations

import os
import re
import statistics
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config
from .agents.safety import ALLOWLIST
from .cloud.faults import FAULTS, KNOWN_FAULTS
from .cloud.simulator import DEPENDENCIES
from .engine import Engine

WEB_DIR = config.ROOT / "web"
EVAL_DIR = config.ROOT / "docs" / "evaluation"
engine: Engine | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global engine
    engine = Engine()
    engine.start()
    yield
    engine.stop()


app = FastAPI(title="NeuroSRE", version="1.0", lifespan=lifespan)


def eng() -> Engine:
    if engine is None:
        raise HTTPException(503, "engine is starting")
    return engine


def fault_title(incident_type: str | None) -> str:
    if not incident_type:
        return "Investigating"
    if incident_type == "unknown":
        return "Unrecognised fault"
    spec = FAULTS.get(incident_type)
    return spec.title.replace(" (no runbook)", "") if spec else incident_type.replace("_", " ").capitalize()


def summary(rec: dict) -> dict:
    """Small view of an incident for the queue."""
    tri = next((e["detail"] for e in rec["timeline"] if e["agent"] == "Triage"), {})
    rep = rec.get("report") or {}
    return {
        "id": rec["id"], "service": rec["service"], "status": rec["status"], "stage": rec.get("stage"),
        "title": fault_title(rep.get("incident_type") or tri.get("incident_type")),
        "severity": rep.get("severity") or tri.get("severity"),
        "opened": rec["opened"], "mttr": rep.get("mttr_seconds"),
        "actions": [a["action"] for a in rep.get("actions", [])],
        "reason": rep.get("escalation_reason"),
    }


# ---------------------------------------------------------------- reads
@app.get("/api/state")
def state(since: int = 0):
    e = eng()
    snap = e.cloud.snapshot()
    with e.lock:
        recs = sorted(e.incidents.values(), key=lambda r: r["opened"], reverse=True)
        incidents = [summary(r) for r in recs]
    resolved = [i for i in incidents if i["status"] == "resolved" and i["mttr"] is not None]
    logs = e.cloud.recent_logs(limit=80, since_seq=since)
    return {
        "now": time.time(),
        "llm": {"label": e.llm.label, "enabled": e.llm.enabled, "model": e.llm.model_name,
                "backup_used": e.llm.backup_used, "failures": e.llm.failures, "calls": e.llm.calls},
        "kb": {"backend": e.kb.backend, "runbooks": len(e.kb.runbooks), "chunks": len(e.kb.chunks)},
        "settings": {"auto": e.auto_faults, "interval": e.auto_interval,
                     "hard": e.cloud.log_style == "paraphrased"},
        "services": [{k: v for k, v in s.items() if k != "base_replicas"}
                     for s in snap.values()],
        "dependencies": DEPENDENCIES,
        "logs": logs,
        "incidents": incidents[:60],
        "quarantined": sorted(e.quarantined),
        "kpis": {
            "healthy": sum(s["status"] == "healthy" for s in snap.values()), "total": len(snap),
            "open": sum(i["status"] in ("investigating", "awaiting_approval") for i in incidents),
            "awaiting": sum(i["status"] == "awaiting_approval" for i in incidents),
            "resolved": len([i for i in incidents if i["status"] == "resolved"]),
            "escalated": sum(i["status"] in ("escalated", "blocked") for i in incidents),
            "mttr_median": statistics.median([i["mttr"] for i in resolved]) if resolved else None,
        },
    }


@app.get("/api/incidents/{iid}")
def incident(iid: str):
    e = eng()
    with e.lock:
        rec = e.incidents.get(iid)
        if not rec:
            raise HTTPException(404, "unknown incident")
        st = rec.get("state") or {}
        data = {
            **summary(rec), "timeline": list(rec["timeline"]), "pending": rec.get("pending"),
            "report": rec.get("report"), "true_fault": rec.get("true_fault"),
            "triage": st.get("triage"), "diagnosis": st.get("diagnosis"), "retrieved": st.get("retrieved", []),
            "plan": st.get("plan", []), "verdicts": st.get("verdicts", []), "risk": st.get("risk"),
            "executions": st.get("executions", []), "attempts": st.get("attempts", 0),
            "escalation_reason": st.get("escalation_reason"), "approved_by": st.get("approved_by"),
            "signals": (st.get("alert") or {}).get("signals", []),
        }
    rb = e.kb.get((data["diagnosis"] or {}).get("runbook_id") or "")
    data["runbook"] = {"id": rb.id, "title": rb.title, "services": rb.services} if rb else None
    return data


@app.get("/api/faults")
def faults():
    return [{"id": f.id, "title": f.title, "targets": f.targets, "known": f.known} for f in FAULTS.values()]


@app.get("/api/policy")
def policy():
    return [{"action": a, "risk": p.risk, "description": p.description,
             "limits": {k: list(v) for k, v in (p.params or {}).items()}, "applies_to": list(p.kinds or [])}
            for a, p in ALLOWLIST.items()]


@app.post("/api/redteam")
def redteam():
    return eng().red_team()


@app.get("/api/runbooks")
def runbooks():
    return [{"id": rb.id, "title": rb.title, "incident_type": rb.incident_type, "severity": rb.severity,
             "services": rb.services, "commands": rb.commands} for rb in eng().kb.runbooks.values()]


@app.get("/api/runbooks/{rid}")
def runbook(rid: str):
    rb = eng().kb.get(rid)
    if not rb:
        raise HTTPException(404, "unknown runbook")
    return {"id": rb.id, "title": rb.title, "text": rb.text, "services": rb.services, "severity": rb.severity}


@app.get("/api/search")
def search(q: str, k: int = 3):
    return [h.as_dict() for h in eng().kb.search(q[:500], k=max(1, min(k, 6)))]


@app.get("/api/metrics")
def metrics():
    rows = eng().store.all()
    by_type: dict[str, dict] = {}
    for r in rows:
        t = by_type.setdefault(r["true_fault"] or "unknown", {"runs": 0, "resolved": 0, "escalated": 0, "triage_ok": 0})
        t["runs"] += 1
        t["resolved"] += r["status"] == "resolved"
        t["escalated"] += r["status"] in ("escalated", "blocked")
        expected = r["true_fault"] if r["true_fault"] in KNOWN_FAULTS else "unknown"
        t["triage_ok"] += r["incident_type"] == expected
    mttr = [r["mttr_seconds"] for r in rows if r["mttr_seconds"] is not None]
    return {
        "total": len(rows), "resolved": sum(r["status"] == "resolved" for r in rows),
        "escalated": sum(r["status"] in ("escalated", "blocked") for r in rows),
        "mttr": mttr[:60], "by_type": by_type,
        "recent": [{"id": r["incident_id"], "service": r["service"], "type": r["incident_type"],
                    "truth": r["true_fault"], "status": r["status"], "mttr": r["mttr_seconds"],
                    "runbook": r["runbook_id"], "approval": r["approval"], "mode": r["mode"],
                    "at": r["detected_at"]} for r in rows[:40]],
        "benchmarks": benchmark_headlines(),
    }


def benchmark_headlines() -> list[dict]:
    """Headline rows of the committed benchmark reports, if any."""
    out = []
    for path in sorted(EVAL_DIR.glob("report_*.md")):
        text = path.read_text(encoding="utf-8")
        title = (re.search(r"^# (.+)$", text, re.M) or [None, path.stem])[1]
        head = text.split("## Headline", 1)[-1].split("##", 1)[0]
        rows = [[c.replace("**", "").strip() for c in line.strip("|").split("|")] for line in head.splitlines()
                if line.startswith("|") and "---" not in line and "Metric" not in line]
        out.append({"file": path.name, "title": title, "rows": rows})
    return out


# ---------------------------------------------------------------- actions
class InjectReq(BaseModel):
    fault: str | None = None
    service: str | None = None
    injection: bool = False


class SettingsReq(BaseModel):
    auto: bool | None = None
    interval: float | None = Field(default=None, ge=10, le=600)
    hard: bool | None = None


class DecisionReq(BaseModel):
    approve: bool
    by: str = Field(min_length=2, max_length=60)


@app.post("/api/inject")
def inject(req: InjectReq):
    e = eng()
    if req.fault is not None:
        spec = FAULTS.get(req.fault)
        if not spec or (req.service and req.service not in spec.targets):
            raise HTTPException(400, "unknown fault or invalid target")
    f = e.inject(req.fault, req.service, prompt_injection=req.injection)
    if not f:
        raise HTTPException(409, "that service already has an active fault")
    return {"fault": f.spec.id, "title": f.spec.title, "service": f.service}


@app.post("/api/settings")
def settings(req: SettingsReq):
    e = eng()
    if req.auto is not None:
        e.auto_faults = req.auto
    if req.interval is not None:
        e.auto_interval = req.interval
    if req.hard is not None:
        e.cloud.log_style, e.cloud.noise = ("paraphrased", 0.6) if req.hard else ("standard", 0.0)
    return state(since=10**12)["settings"]


@app.post("/api/incidents/{iid}/decision")
def decision(iid: str, req: DecisionReq):
    e = eng()
    rec = e.incidents.get(iid)
    if not rec:
        raise HTTPException(404, "unknown incident")
    if rec["status"] != "awaiting_approval":
        raise HTTPException(409, "this incident is not waiting for approval")
    e.decide(iid, req.approve, by=req.by.strip())
    return {"ok": True}


@app.post("/api/services/{name}/fix")
def manual_fix(name: str):
    e = eng()
    if name not in e.cloud.services:
        raise HTTPException(404, "unknown service")
    e.manual_fix(name)
    return {"ok": True}


# ---------------------------------------------------------------- web console
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("neurosre.api:app", host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")))
