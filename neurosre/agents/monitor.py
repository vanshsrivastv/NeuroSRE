"""Anomaly detection used by the Monitor agent and the Verifier agent.

Works only on *observable* signals (metrics + logs), never on the simulator's
internal fault record, so detection and verification are honest.
"""
from __future__ import annotations

from ..cloud.simulator import BASELINE

THRESHOLDS = {"cpu": 85.0, "memory": 90.0, "disk": 90.0, "error_rate": 10.0}


def signals_for(service: str, m: dict) -> list[str]:
    """Return human-readable anomaly signals for one service's metrics."""
    sig = []
    if m.get("status") == "down":
        sig.append("service DOWN (health check failing)")
    for k, limit in THRESHOLDS.items():
        if m.get(k, 0) >= limit:
            sig.append(f"{k}={m[k]} (threshold {limit})")
    base_lat = BASELINE[service]["latency_ms"]
    if m.get("latency_ms", 0) >= base_lat * 5:
        sig.append(f"latency_ms={m['latency_ms']} (baseline {base_lat})")
    if m.get("queue_depth", 0) > 10_000:
        sig.append(f"queue_depth={m['queue_depth']}")
    if m.get("pool_size") and m.get("connections", 0) >= 0.95 * m["pool_size"]:
        sig.append(f"connections={m['connections']}/{m['pool_size']}")
    return sig


def flatten(state: dict) -> dict:
    return {k: v for k, v in state.items() if k not in ("extra", "name")} | state.get("extra", {})


def detect(snapshot: dict[str, dict], skip: set[str] | None = None) -> list[dict]:
    """Scan all services and return one alert per anomalous service."""
    alerts = []
    for name, st in snapshot.items():
        if skip and name in skip:
            continue
        m = flatten(st)
        sig = signals_for(name, m)
        if sig:
            alerts.append({"service": name, "signals": sig, "metrics": m})
    return alerts


def is_healthy(service: str, state: dict) -> tuple[bool, list[str]]:
    sig = signals_for(service, flatten(state))
    return (not sig and state.get("status") == "healthy"), sig
