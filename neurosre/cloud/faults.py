"""Catalogue of injectable faults.

Each fault describes how it distorts a service's metrics, which log lines it
produces, and which remediation actions are *really* required to clear it.
The simulator only recovers a service when every required action has been
applied with acceptable parameters, so a wrong or incomplete fix is visible
to the Verifier agent.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

APP_SERVICES = ["api-gateway", "auth-service", "payment-service"]


@dataclass(frozen=True)
class FaultSpec:
    id: str
    title: str
    targets: list[str]
    required: dict[str, Callable[[dict, dict], bool]]   # action -> param check(params, service_state)
    effects: dict[str, tuple[float, float]]               # metric -> (min, max) while active
    status: str                                           # "degraded" or "down"
    logs: list[tuple[str, str]]                           # (level, template)
    extra: dict[str, tuple[float, float]] = field(default_factory=dict)
    known: bool = True          # False = no runbook exists; only a human can fix it


def _any(_p, _s):
    return True


def _scaled_up(p, s):
    return int(p.get("replicas", 0)) >= max(4, s["base_replicas"] + 2)


def _pool_raised(p, s):
    return int(p.get("size", 0)) >= 150          # at least 1.5x the default pool of 100


FAULTS: dict[str, FaultSpec] = {f.id: f for f in [
    FaultSpec(
        "high_cpu", "CPU saturation from traffic spike", APP_SERVICES,
        {"scale_service": _scaled_up},
        {"cpu": (91, 99), "latency_ms": (900, 1800), "error_rate": (3, 8)}, "degraded",
        [("WARN", "CPU throttling detected: container at {cpu:.0f}% of limit"),
         ("WARN", "request queue growing, p99 latency {latency_ms:.0f}ms"),
         ("ERROR", "upstream request timed out after 1500ms (rps={rps})")]),
    FaultSpec(
        "memory_leak", "Memory leak in application process", APP_SERVICES,
        {"restart_service": _any},
        {"memory": (93, 99), "latency_ms": (400, 900), "error_rate": (4, 12)}, "degraded",
        [("WARN", "heap usage {memory:.0f}% after full GC, GC overhead limit approaching"),
         ("ERROR", "java.lang.OutOfMemoryError: Java heap space in RequestCache.put"),
         ("WARN", "resident memory grew 180MB in the last 10 minutes without traffic increase")]),
    FaultSpec(
        "disk_full", "Disk full due to log growth", list(APP_SERVICES) + ["orders-db"],
        {"rotate_logs": _any, "clear_tmp": _any},
        {"disk": (97, 100), "error_rate": (10, 25)}, "degraded",
        [("ERROR", "write /var/log/app/app.log: No space left on device"),
         ("ERROR", "failed to persist session file: ENOSPC"),
         ("WARN", "filesystem /var usage at {disk:.0f}%")]),
    FaultSpec(
        "service_crash", "Service process crashed (crash loop)", APP_SERVICES,
        {"restart_service": _any},
        {"error_rate": (100, 100), "cpu": (0, 2)}, "down",
        [("ERROR", "process exited with code 139 (segmentation fault)"),
         ("ERROR", "health check failed: connection refused on :8080"),
         ("ERROR", "container restarting: CrashLoopBackOff (restart count {restarts})")]),
    FaultSpec(
        "db_connection_exhausted", "Database connection pool exhausted", ["orders-db"],
        {"kill_idle_connections": _any, "increase_pool": _pool_raised},
        {"error_rate": (20, 40), "latency_ms": (2000, 5000)}, "degraded",
        [("ERROR", "FATAL: sorry, too many clients already ({connections}/{pool_size})"),
         ("ERROR", "payment-service: timeout acquiring connection from pool after 30000ms"),
         ("WARN", "{idle} connections idle in transaction for more than 10 minutes")],
        extra={"connections_ratio": (1.0, 1.0)}),
    FaultSpec(
        "slow_queries", "Long-running queries blocking the database", ["orders-db"],
        {"kill_long_queries": _any},
        {"cpu": (88, 97), "latency_ms": (3000, 9000), "error_rate": (8, 15)}, "degraded",
        [("WARN", "slow query 14.2s: SELECT * FROM orders WHERE customer_note LIKE '%gift%' (seq scan)"),
         ("WARN", "lock wait timeout exceeded on table orders"),
         ("ERROR", "statement timeout: query running for 92s cancelled by client")]),
    FaultSpec(
        "tls_cert_expired", "Expired TLS certificate", ["api-gateway"],
        {"renew_certificate": _any},
        {"error_rate": (55, 70)}, "degraded",
        [("ERROR", "TLS handshake failed: x509: certificate has expired or is not yet valid"),
         ("ERROR", "client rejected connection: SSL_ERROR_EXPIRED_CERT_ALERT"),
         ("WARN", "certificate for api.neurosre.local expired {cert_days_ago} day(s) ago")]),
    FaultSpec(
        "cache_failure", "Cache server down", ["redis-cache"],
        {"restart_service": _any},
        {"error_rate": (100, 100), "cpu": (0, 1)}, "down",
        [("ERROR", "Could not connect to Redis at redis-cache:6379: Connection refused"),
         ("WARN", "api-gateway: cache unavailable, falling back to database (latency +300%)"),
         ("ERROR", "redis-server terminated unexpectedly (signal 11)")]),
    FaultSpec(
        "queue_backlog", "Message queue backlog", ["worker-queue"],
        {"scale_service": _scaled_up},
        {"cpu": (85, 95), "latency_ms": (5000, 15000), "error_rate": (2, 6)}, "degraded",
        [("WARN", "queue depth {queue_depth} messages, consumer lag growing"),
         ("WARN", "oldest unprocessed message is 640s old"),
         ("ERROR", "job timed out waiting in queue: order-confirmation-email")],
        extra={"queue_depth": (25000, 60000)}),
    FaultSpec(
        "bad_deployment", "Faulty release deployed", APP_SERVICES,
        {"rollback_deployment": _any},
        {"error_rate": (30, 45), "latency_ms": (300, 700)}, "degraded",
        [("INFO", "deployment {version} rolled out to all replicas"),
         ("ERROR", "NullPointerException at CheckoutHandler.applyDiscount (version {version})"),
         ("ERROR", "HTTP 500 rate increased sharply since deploy {version}")]),
    FaultSpec(
        "db_primary_failure", "Database primary node failure", ["orders-db"],
        {"failover_database": _any},
        {"error_rate": (100, 100), "cpu": (0, 1)}, "down",
        [("ERROR", "primary node orders-db-0 unreachable: no route to host"),
         ("ERROR", "could not connect to server: Connection timed out (primary)"),
         ("WARN", "replica orders-db-1 healthy, replication lag 0.4s, ready for promotion")]),
    FaultSpec(
        "dns_failure", "Internal DNS resolution failure", APP_SERVICES,
        {"flush_dns_cache": _any},
        {"error_rate": (35, 60)}, "degraded",
        [("ERROR", "getaddrinfo ENOTFOUND orders-db.internal"),
         ("ERROR", "Temporary failure in name resolution: redis-cache.internal"),
         ("WARN", "stale DNS cache entry for auth-service.internal (TTL expired)")]),
    # ---- faults with NO runbook: the correct behaviour is to escalate, not to guess a fix
    FaultSpec(
        "clock_skew", "System clock drift (no runbook)", ["auth-service", "payment-service"],
        {"manual_intervention": _any},
        {"error_rate": (30, 50)}, "degraded",
        [("ERROR", "JWT rejected: token issued in the future (iat > now + 300s)"),
         ("WARN", "system clock offset +341s from NTP reference"),
         ("ERROR", "kerberos: clock skew too great while validating ticket")], known=False),
    FaultSpec(
        "network_partition", "Partial network partition between zones (no runbook)", ["api-gateway"],
        {"manual_intervention": _any},
        {"error_rate": (25, 45), "latency_ms": (2000, 6000)}, "degraded",
        [("ERROR", "connection reset by peer while proxying to payment-service:8080"),
         ("WARN", "TCP retransmission rate 14% on eth0"),
         ("ERROR", "upstream payment-service unreachable from zone ap-south-1b (zone ap-south-1a healthy)")],
        known=False),
]}
KNOWN_FAULTS = [f for f, spec in FAULTS.items() if spec.known]
