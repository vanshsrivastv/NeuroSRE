"""Deterministic rule-based fallbacks used when no LLM is available.

They make the system usable offline and act as a baseline to compare the
LLM agents against.
"""
from __future__ import annotations

SIGNATURES: dict[str, list[str]] = {
    "high_cpu": ["cpu throttling", "request queue growing", "timed out after 1500ms"],
    "memory_leak": ["outofmemoryerror", "heap usage", "gc overhead", "resident memory grew"],
    "disk_full": ["no space left", "enospc", "filesystem /var usage"],
    "service_crash": ["crashloopbackoff", "exited with code", "connection refused on :8080"],
    "db_connection_exhausted": ["too many clients", "acquiring connection", "idle in transaction"],
    "slow_queries": ["slow query", "lock wait timeout", "statement timeout"],
    "tls_cert_expired": ["x509", "certificate", "ssl_error"],
    "cache_failure": ["redis", "6379", "cache unavailable"],
    "queue_backlog": ["queue depth", "consumer lag", "waiting in queue"],
    "bad_deployment": ["deployment v", "nullpointerexception", "since deploy"],
    "db_primary_failure": ["primary node", "ready for promotion", "(primary)"],
    "dns_failure": ["enotfound", "name resolution", "stale dns"],
}
SEVERITY = {"service_crash": "P1", "disk_full": "P1", "db_connection_exhausted": "P1", "tls_cert_expired": "P1",
            "bad_deployment": "P1", "db_primary_failure": "P1", "queue_backlog": "P3"}


def classify(log_lines: list[str]) -> tuple[str, float]:
    text = "\n".join(log_lines).lower()
    scores = {t: sum(text.count(k) for k in keys) for t, keys in SIGNATURES.items()}
    best = max(scores, key=scores.get)
    total = sum(scores.values())
    if scores[best] == 0:
        return "unknown", 0.0
    return best, round(scores[best] / total, 2)


def severity(incident_type: str) -> str:
    return SEVERITY.get(incident_type, "P2")
