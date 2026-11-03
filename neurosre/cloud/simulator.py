"""A small, stateful mock cloud.

Six services expose live metrics and emit JSON-style log records. Faults can be
injected; remediation commands change the state of the services. A fault is
only cleared when *all* of its required actions have been applied with valid
parameters, so recovery is real, observable and verifiable.
"""
from __future__ import annotations

import itertools
import random
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field

from .faults import FAULTS, PARAPHRASES, FaultSpec

BASELINE = {
    "api-gateway":     dict(kind="gateway",  cpu=35, memory=45, disk=40, latency_ms=80,  error_rate=0.3, replicas=3),
    "auth-service":    dict(kind="app",      cpu=25, memory=50, disk=35, latency_ms=60,  error_rate=0.2, replicas=2),
    "payment-service": dict(kind="app",      cpu=30, memory=55, disk=38, latency_ms=120, error_rate=0.4, replicas=2),
    "orders-db":       dict(kind="database", cpu=40, memory=65, disk=55, latency_ms=15,  error_rate=0.1, replicas=2),
    "redis-cache":     dict(kind="cache",    cpu=15, memory=60, disk=20, latency_ms=2,   error_rate=0.0, replicas=1),
    "worker-queue":    dict(kind="queue",    cpu=30, memory=40, disk=30, latency_ms=200, error_rate=0.2, replicas=2),
}
BASE_EXTRA = {
    "orders-db": {"pool_size": 100, "connections": 42},
    "worker-queue": {"queue_depth": 120},
    "api-gateway": {"cert_days_left": 64},
}
INFO_LOGS = {
    "api-gateway": ["GET /api/v1/orders 200 {lat}ms", "POST /api/v1/checkout 201 {lat}ms", "GET /health 200 3ms"],
    "auth-service": ["token issued for user u-{n}", "session refreshed for user u-{n}", "GET /health 200 2ms"],
    "payment-service": ["payment authorised txn-{n} amount=₹{amt}", "refund processed txn-{n}", "GET /health 200 4ms"],
    "orders-db": ["checkpoint complete: wrote {n} buffers", "autovacuum: processed table orders", "replication lag 0.2s"],
    "redis-cache": ["keyspace hits={n} misses={m}", "background save completed", "connected clients: {m}"],
    "worker-queue": ["job completed: order-confirmation-email #{n}", "job completed: invoice-pdf #{n}", "consumer heartbeat ok"],
}


@dataclass
class ActiveFault:
    spec: FaultSpec
    service: str
    started: float = field(default_factory=time.time)
    applied: set = field(default_factory=set)
    context: dict = field(default_factory=dict)

    @property
    def resolved(self) -> bool:
        return set(self.spec.required) <= self.applied


class CloudSimulator:
    def __init__(self, seed: int | None = None, log_style: str = "standard", noise: float = 0.0):
        """log_style: "standard" or "paraphrased" (held-out wording for evaluation).
        noise: per-tick probability of a misleading log line from an unrelated fault."""
        self.rng = random.Random(seed)
        self.log_style = log_style
        self.noise = noise
        self.lock = threading.RLock()
        self.logs: deque[dict] = deque(maxlen=600)
        self._seq = itertools.count(1)
        self.services: dict[str, dict] = {}
        self.faults: dict[str, ActiveFault] = {}
        self.command_history: list[dict] = []
        for name, b in BASELINE.items():
            self.services[name] = self._fresh_state(name, b)

    # ------------------------------------------------------------------ state
    def _fresh_state(self, name: str, b: dict) -> dict:
        return {
            "name": name, "kind": b["kind"], "status": "healthy",
            "cpu": b["cpu"], "memory": b["memory"], "disk": b["disk"],
            "latency_ms": b["latency_ms"], "error_rate": b["error_rate"],
            "replicas": b["replicas"], "base_replicas": b["replicas"],
            "version": "v2.4.0", "restarts": 0,
            "extra": dict(BASE_EXTRA.get(name, {})),
        }

    def snapshot(self) -> dict[str, dict]:
        with self.lock:
            return {k: {**v, "extra": dict(v["extra"])} for k, v in self.services.items()}

    def health(self, service: str) -> dict:
        with self.lock:
            s = self.services[service]
            return {k: s[k] for k in ("status", "cpu", "memory", "disk", "latency_ms", "error_rate", "replicas")} | s["extra"]

    def is_healthy(self, service: str) -> bool:
        with self.lock:
            return self.services[service]["status"] == "healthy" and service not in self.faults

    # ------------------------------------------------------------------ faults
    def inject(self, fault_id: str | None = None, service: str | None = None) -> ActiveFault | None:
        with self.lock:
            if fault_id is None:
                # random chaos uses known faults; unknown ones are injected explicitly
                options = [(f, s) for f in FAULTS.values() if f.known for s in f.targets if s not in self.faults]
                if not options:
                    return None
                spec, service = self.rng.choice(options)
            else:
                spec = FAULTS[fault_id]
                service = service or self.rng.choice([s for s in spec.targets if s not in self.faults] or spec.targets)
            if service in self.faults:
                return None
            fault = ActiveFault(spec, service)
            st = self.services[service]
            if spec.id == "bad_deployment":
                fault.context["previous_version"] = st["version"]
                st["version"] = "v2.5.0"
            if spec.id == "tls_cert_expired":
                st["extra"]["cert_days_left"] = -1
            self.faults[service] = fault
            self._apply_fault_effects(fault)
            first = self._templates(spec)[0]
            self._log(service, first[0], self._render(fault, first[1]))
            return fault

    def _apply_fault_effects(self, fault: ActiveFault) -> None:
        st = self.services[fault.service]
        st["status"] = fault.spec.status
        for metric, (lo, hi) in fault.spec.effects.items():
            st[metric] = round(self.rng.uniform(lo, hi), 1)
        if fault.spec.id == "db_connection_exhausted":
            st["extra"]["connections"] = st["extra"]["pool_size"]
        if fault.spec.id == "queue_backlog":
            st["extra"]["queue_depth"] = int(self.rng.uniform(*fault.spec.extra["queue_depth"]))
        if fault.spec.status == "down":
            st["restarts"] += 1

    def _templates(self, spec: FaultSpec) -> list[tuple[str, str]]:
        return PARAPHRASES[spec.id] if self.log_style == "paraphrased" else spec.logs

    def _red_herring(self, fault: ActiveFault) -> None:
        """A misleading WARN line borrowed from an unrelated fault (real logs are noisy)."""
        other = self.rng.choice([f for f in FAULTS.values() if f.id != fault.spec.id and f.known])
        _, tpl = self.rng.choice(self._templates(other)[1:] if other.id == "bad_deployment" else self._templates(other))
        self._log(fault.service, "WARN", self._render(fault, tpl))

    def _render(self, fault: ActiveFault, template: str) -> str:
        st = self.services[fault.service]
        vals = {**st, **st["extra"], "rps": self.rng.randint(800, 2400), "idle": self.rng.randint(30, 70),
                "cert_days_ago": 1, "version": st["version"]}
        try:
            return template.format(**vals)
        except (KeyError, ValueError):
            return template

    # ------------------------------------------------------------------ commands
    def execute(self, action: str, target: str, params: dict | None = None) -> dict:
        """Apply a remediation command. Returns a result record."""
        params = params or {}
        with self.lock:
            if target not in self.services:
                return self._record(action, target, params, False, f"unknown service '{target}'")
            st = self.services[target]
            handler = getattr(self, f"_cmd_{action}", None)
            if handler is None:
                return self._record(action, target, params, False, f"unknown command '{action}'")
            fault = self.faults.get(target)
            # judge the fix against the state *before* the command changes it
            fixes = bool(fault and action in fault.spec.required and fault.spec.required[action](params, st))
            ok, msg = handler(st, params)
            if ok and fixes:
                fault.applied.add(action)
                if fault.resolved:
                    self._recover(target)
                    msg += " | service recovered"
            self._log(target, "INFO", f"[neuroctl] {action} {params or ''} -> {msg}".replace(" {}", ""))
            return self._record(action, target, params, ok, msg)

    def _record(self, action, target, params, ok, msg) -> dict:
        rec = {"ts": time.time(), "action": action, "target": target, "params": params, "ok": ok, "message": msg}
        self.command_history.append(rec)
        return rec

    def _recover(self, service: str) -> None:
        self.faults.pop(service, None)
        b, st = BASELINE[service], self.services[service]
        for k in ("cpu", "memory", "disk", "latency_ms", "error_rate"):
            st[k] = b[k]
        st["status"] = "healthy"
        st["extra"].update({k: v for k, v in BASE_EXTRA.get(service, {}).items() if k not in ("pool_size",)})

    # each command returns (ok, message); state changes are partial unless the fault is fully fixed
    def _cmd_restart_service(self, st, p):
        st["memory"] = BASELINE[st["name"]]["memory"]; st["restarts"] += 1
        return True, f"{st['name']} restarted ({st['replicas']} replicas)"

    def _cmd_scale_service(self, st, p):
        n = int(p.get("replicas", st["replicas"]))
        st["replicas"] = n
        return True, f"{st['name']} scaled to {n} replicas"

    def _cmd_rotate_logs(self, st, p):
        st["disk"] = max(st["disk"] - 12, BASELINE[st["name"]]["disk"])
        return True, "logs rotated and compressed"

    def _cmd_clear_tmp(self, st, p):
        st["disk"] = max(st["disk"] - 10, BASELINE[st["name"]]["disk"])
        return True, "/tmp cleaned"

    def _cmd_kill_idle_connections(self, st, p):
        if "connections" in st["extra"]:
            st["extra"]["connections"] = int(st["extra"]["connections"] * 0.6)
        return True, "idle-in-transaction connections terminated"

    def _cmd_increase_pool(self, st, p):
        if "pool_size" not in st["extra"]:
            return False, "service has no connection pool"
        st["extra"]["pool_size"] = int(p.get("size", st["extra"]["pool_size"]))
        return True, f"connection pool size set to {st['extra']['pool_size']}"

    def _cmd_kill_long_queries(self, st, p):
        return True, "queries running longer than 30s terminated"

    def _cmd_renew_certificate(self, st, p):
        st["extra"]["cert_days_left"] = 90
        return True, "certificate renewed, valid for 90 days"

    def _cmd_flush_cache(self, st, p):
        return True, "cache flushed"

    def _cmd_flush_dns_cache(self, st, p):
        return True, "DNS resolver cache flushed"

    def _cmd_rollback_deployment(self, st, p):
        fault = self.faults.get(st["name"])
        prev = fault.context.get("previous_version", "v2.4.0") if fault else "v2.4.0"
        st["version"] = prev
        return True, f"rolled back to {prev}"

    def _cmd_failover_database(self, st, p):
        if st["kind"] != "database":
            return False, "not a database"
        return True, "replica orders-db-1 promoted to primary"

    # ------------------------------------------------------------------ logs
    def _log(self, service: str, level: str, message: str) -> None:
        self.logs.append({"seq": next(self._seq), "ts": time.time(), "service": service, "level": level,
                          "message": message, "trace_id": uuid.uuid4().hex[:12]})

    def tick(self) -> None:
        """Advance the simulation: jitter metrics and emit a batch of log lines."""
        with self.lock:
            for name, st in self.services.items():
                b = BASELINE[name]
                fault = self.faults.get(name)
                if fault:
                    self._apply_fault_effects(fault)
                    for _ in range(self.rng.randint(1, 2)):
                        # the first template of a deployment fault is a one-off event, not a repeating symptom
                        logs = self._templates(fault.spec)
                        pool = logs[1:] if fault.spec.id == "bad_deployment" else logs
                        level, tpl = self.rng.choice(pool)
                        self._log(name, level, self._render(fault, tpl))
                    if self.noise and self.rng.random() < self.noise:
                        self._red_herring(fault)
                else:
                    for k in ("cpu", "memory"):
                        st[k] = round(max(1, b[k] + self.rng.uniform(-5, 5)), 1)
                    st["latency_ms"] = round(b["latency_ms"] * self.rng.uniform(0.85, 1.2), 1)
                    st["error_rate"] = round(max(0, b["error_rate"] + self.rng.uniform(-0.2, 0.3)), 2)
                    if self.rng.random() < 0.5:
                        tpl = self.rng.choice(INFO_LOGS[name])
                        self._log(name, "INFO", tpl.format(lat=int(st["latency_ms"]), n=self.rng.randint(1000, 9999),
                                                          m=self.rng.randint(10, 99), amt=self.rng.randint(99, 9999)))

    def recent_logs(self, service: str | None = None, limit: int = 30, since_seq: int = 0) -> list[dict]:
        with self.lock:
            items = [l for l in self.logs if l["seq"] > since_seq and (service is None or l["service"] == service)]
            return items[-limit:]
