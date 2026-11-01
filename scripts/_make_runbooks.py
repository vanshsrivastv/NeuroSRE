"""One-off generator for the runbook knowledge base (kept for reference).

Run:  python scripts/_make_runbooks.py
"""
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "neurosre" / "knowledge" / "runbooks"

RUNBOOKS = [
    ("RB-001", "high_cpu", "api-gateway, auth-service, payment-service", "P2",
     "High CPU Utilisation from Traffic Spike",
     """- CPU usage above 90% on most replicas; container CPU throttling messages.
- p99 latency several times higher than normal; request queue growing.
- Upstream request timeouts while memory and disk look normal.""",
     """A sudden increase in incoming requests (marketing campaign, retry storm or bot traffic) exceeds the capacity
of the current replica count. The service is healthy but under-provisioned.""",
     """1. Confirm CPU is high on all replicas, not just one (one hot replica suggests a stuck thread instead).
2. Check requests per second against the normal baseline.
3. Make sure memory is normal, which rules out a memory leak causing GC pressure.""",
     ["scale_service {service} replicas=5"],
     "CPU falls below 70% and p99 latency returns to baseline within 2 minutes of scaling.",
     "Scale back to the original replica count once traffic normalises.",
     "Escalate if CPU stays above 90% after scaling to 8 replicas, as it may be a code-level regression."),
    ("RB-002", "memory_leak", "api-gateway, auth-service, payment-service", "P2",
     "Memory Leak in Application Process",
     """- Heap / resident memory steadily climbing to more than 90% without a traffic increase.
- Frequent full garbage collections, "GC overhead limit" warnings.
- java.lang.OutOfMemoryError or similar allocation failures in logs.""",
     """An in-process cache or listener is retaining objects that are never released. Memory grows until the process
thrashes in garbage collection and starts failing requests.""",
     """1. Compare memory growth with traffic; leak if memory rises while traffic is flat.
2. Look for OutOfMemoryError and GC overhead messages.
3. Note the last deployment time; capture a heap dump if possible for developers.""",
     ["restart_service {service}"],
     "Memory drops back to baseline (around 50%) and error rate returns below 1%.",
     "None required; a restart is non-destructive.",
     "Open a bug for the owning team with the heap dump; escalate if leak returns within 1 hour."),
    ("RB-003", "disk_full", "api-gateway, auth-service, payment-service, orders-db", "P1",
     "Disk Full due to Log Growth",
     """- Filesystem usage at 97-100%.
- Errors such as "No space left on device" or ENOSPC when writing files.
- Writes failing while CPU and memory are normal.""",
     """Application logs and temporary files have filled the volume because log rotation did not run or debug logging
was left enabled.""",
     """1. Check which mount is full (usually /var/log or /tmp).
2. Identify the largest files; confirm they are logs or temporary files, never data files.""",
     ["rotate_logs {service}", "clear_tmp {service}"],
     "Disk usage drops below 70% and write errors stop.",
     "Not applicable; rotated logs are archived, not deleted.",
     "Escalate if data files (not logs) are filling the disk; never delete data files automatically."),
    ("RB-004", "service_crash", "api-gateway, auth-service, payment-service", "P1",
     "Service Crash / CrashLoopBackOff",
     """- Service status DOWN, health checks failing with "connection refused".
- Process exited with a non-zero code (for example 139 segmentation fault).
- Container restarting repeatedly (CrashLoopBackOff), error rate 100%.""",
     """The process crashed because of a transient fault (bad request, native library crash) and the container did not
come back cleanly.""",
     """1. Check the exit code and the last log lines before the crash.
2. Check whether a deployment happened recently; if yes see RB-010 (Faulty Release).""",
     ["restart_service {service}"],
     "Health check returns 200 and the service status is HEALTHY.",
     "Not applicable.",
     "If the service crashes again within 10 minutes, escalate to the owning team."),
    ("RB-005", "db_connection_exhausted", "orders-db", "P1",
     "Database Connection Pool Exhausted",
     """- Database rejects new clients: "too many clients already".
- Application services time out acquiring a connection from the pool.
- Many sessions "idle in transaction" for a long time.""",
     """Connections are leaked by clients that open a transaction and never close it, so the database reaches its
maximum connection limit.""",
     """1. Count active vs idle-in-transaction sessions.
2. Compare current connections with the configured pool size.""",
     ["kill_idle_connections {service}", "increase_pool {service} size=200"],
     "Connections fall below 80% of the pool size and timeouts stop.",
     "Reduce the pool size back to 100 after the client-side leak is fixed.",
     "Escalate to the application team to fix the connection leak."),
    ("RB-006", "slow_queries", "orders-db", "P2",
     "Long-Running Queries Blocking the Database",
     """- Slow query log shows queries taking many seconds with sequential (full table) scans.
- Lock wait timeouts and statement timeouts.
- High database CPU and latency.""",
     """An unindexed ad-hoc or reporting query scans a large table and holds locks, blocking normal traffic.""",
     """1. List queries running longer than 30 seconds.
2. Confirm they are reporting / ad-hoc queries, not migrations.""",
     ["kill_long_queries {service}"],
     "Database latency returns below 50 ms and lock waits stop.",
     "Not applicable.",
     "Ask the data team to add the missing index; escalate if a schema migration is running."),
    ("RB-007", "tls_cert_expired", "api-gateway", "P1",
     "Expired TLS Certificate",
     """- TLS handshake failures: "x509: certificate has expired".
- Clients report SSL_ERROR_EXPIRED_CERT_ALERT.
- High error rate on the gateway while backend services are healthy.""",
     """The public TLS certificate passed its expiry date because automatic renewal failed.""",
     """1. Check the certificate expiry date on the gateway.
2. Confirm backend services are healthy (the problem is only at the edge).""",
     ["renew_certificate {service}"],
     "TLS handshakes succeed and the gateway error rate returns below 1%.",
     "Not applicable.",
     "Escalate if renewal fails (for example DNS validation errors)."),
    ("RB-008", "cache_failure", "redis-cache", "P2",
     "Cache Server Down",
     """- "Connection refused" when connecting to redis-cache:6379.
- Applications fall back to the database, which increases latency.
- redis-server terminated unexpectedly.""",
     """The cache process crashed. Applications keep working through the database but slower; prolonged outage will
overload the database.""",
     """1. Confirm the cache process is not running.
2. Check database load, since it rises while the cache is down.""",
     ["restart_service {service}"],
     "Cache accepts connections and hit rate starts recovering.",
     "Not applicable.",
     "If the cache crashes repeatedly, escalate and check for memory exhaustion."),
    ("RB-009", "queue_backlog", "worker-queue", "P3",
     "Message Queue Backlog",
     """- Queue depth growing into tens of thousands of messages.
- Consumer lag increasing; jobs time out while waiting in the queue.
- Worker CPU high.""",
     """The number of workers is too low for the incoming job rate, so messages accumulate faster than they are
processed.""",
     """1. Compare the message arrival rate with the processing rate.
2. Confirm workers are processing (not stuck) by checking job completion logs.""",
     ["scale_service {service} replicas=6"],
     "Queue depth starts falling and consumer lag returns to near zero.",
     "Scale workers back down once the backlog is cleared.",
     "Escalate if workers are stuck (no job completions) rather than slow."),
    ("RB-010", "bad_deployment", "api-gateway, auth-service, payment-service", "P1",
     "Faulty Release Deployed",
     """- Sharp increase in HTTP 500 errors immediately after a new version was deployed.
- New exceptions (for example NullPointerException) referencing the new version.
- Infrastructure metrics (CPU, memory, disk) look normal.""",
     """The latest release contains a bug. The fastest safe fix is to roll back to the previous known-good version.""",
     """1. Correlate the error spike with the deployment timestamp.
2. Confirm the errors mention code paths changed in the release.""",
     ["rollback_deployment {service}"],
     "Error rate returns below 1% on the previous version.",
     "Re-deploy the fixed version after the bug is resolved by developers.",
     "Rollback is a HIGH-risk change and needs on-call approval. Notify the release owner."),
    ("RB-011", "db_primary_failure", "orders-db", "P1",
     "Database Primary Node Failure",
     """- Primary database node unreachable ("no route to host", connection timed out).
- All writes failing; error rate 100%.
- Replica healthy with low replication lag.""",
     """The primary database host failed. The healthy replica must be promoted to primary to restore writes.""",
     """1. Confirm the primary is unreachable from more than one client.
2. Confirm the replica is healthy and replication lag is small (less than 1 s) to avoid data loss.""",
     ["failover_database {service}"],
     "Writes succeed against the new primary and error rate returns below 1%.",
     "Rebuild the failed node as a new replica.",
     "Failover is a HIGH-risk change and needs on-call approval. Never fail over if replication lag is large."),
    ("RB-012", "dns_failure", "api-gateway, auth-service, payment-service", "P2",
     "Internal DNS Resolution Failure",
     """- Errors such as "getaddrinfo ENOTFOUND" or "Temporary failure in name resolution".
- Calls to internal hostnames (*.internal) fail while the target services are healthy.
- Stale DNS cache entries.""",
     """The service's local DNS resolver cache holds stale or negative entries after an internal DNS change.""",
     """1. Confirm the target services are healthy, which rules out a real outage.
2. Check whether resolution fails only from this service.""",
     ["flush_dns_cache {service}"],
     "Internal hostnames resolve and the error rate returns to baseline.",
     "Not applicable.",
     "Escalate to the platform team if resolution fails cluster-wide."),
]

TEMPLATE = """---
id: {id}
incident_type: {itype}
services: {services}
severity: {sev}
---
# {title}

## Symptoms
{symptoms}

## Root Cause
{cause}

## Diagnosis Steps
{diag}

## Remediation
Run the following commands with neuroctl, replacing {{service}} with the affected service:
```neuroctl
{cmds}
```

## Verification
{verify}

## Rollback
{rollback}

## Escalation
{esc}
"""

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for rid, itype, services, sev, title, sym, cause, diag, cmds, verify, rollback, esc in RUNBOOKS:
        text = TEMPLATE.format(id=rid, itype=itype, services=services, sev=sev, title=title, symptoms=sym,
                               cause=cause, diag=diag, cmds="\n".join(cmds), verify=verify, rollback=rollback, esc=esc)
        (OUT / f"{rid.lower()}-{itype.replace('_', '-')}.md").write_text(text, encoding="utf-8")
    print(f"wrote {len(RUNBOOKS)} runbooks to {OUT}")
