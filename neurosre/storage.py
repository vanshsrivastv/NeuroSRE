"""SQLite store for incident reports and the audit trail."""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
    incident_id TEXT PRIMARY KEY,
    service TEXT, incident_type TEXT, true_fault TEXT, severity TEXT, summary TEXT,
    runbook_id TEXT, root_cause TEXT, risk TEXT, approval TEXT, status TEXT,
    escalation_reason TEXT, attempts INTEGER, mttr_seconds REAL,
    detected_at REAL, closed_at REAL, mode TEXT, actions TEXT, timeline TEXT, retrieved TEXT
);
"""


class IncidentStore:
    def __init__(self, path: Path | str | None = None):
        self.path = str(path or config.DB_PATH)
        self._lock = threading.Lock()
        with self._conn() as c:
            c.executescript(SCHEMA)

    def _conn(self):
        return sqlite3.connect(self.path, timeout=10)

    def save(self, report: dict, state: dict, true_fault: str | None = None) -> None:
        row = {**{k: report.get(k) for k in ("incident_id", "service", "incident_type", "severity", "summary",
                                             "runbook_id", "root_cause", "risk", "approval", "status",
                                             "escalation_reason", "attempts", "mttr_seconds", "detected_at",
                                             "closed_at", "mode")},
               "true_fault": true_fault,
               "actions": json.dumps(report.get("actions", [])),
               "timeline": json.dumps(state.get("timeline", []), default=str),
               "retrieved": json.dumps(state.get("retrieved", []))}
        cols = ", ".join(row)
        with self._lock, self._conn() as c:
            c.execute(f"INSERT OR REPLACE INTO incidents ({cols}) VALUES ({', '.join('?' * len(row))})",
                      list(row.values()))

    def all(self, limit: int = 500) -> list[dict]:
        with self._conn() as c:
            c.row_factory = sqlite3.Row
            rows = c.execute("SELECT * FROM incidents ORDER BY detected_at DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            for k in ("actions", "timeline", "retrieved"):
                d[k] = json.loads(d[k] or "[]")
            out.append(d)
        return out

    def clear(self) -> None:
        with self._lock, self._conn() as c:
            c.execute("DELETE FROM incidents")
