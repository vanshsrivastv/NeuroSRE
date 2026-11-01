---
id: RB-005
incident_type: db_connection_exhausted
services: orders-db
severity: P1
---
# Database Connection Pool Exhausted

## Symptoms
- Database rejects new clients: "too many clients already".
- Application services time out acquiring a connection from the pool.
- Many sessions "idle in transaction" for a long time.

## Root Cause
Connections are leaked by clients that open a transaction and never close it, so the database reaches its
maximum connection limit.

## Diagnosis Steps
1. Count active vs idle-in-transaction sessions.
2. Compare current connections with the configured pool size.

## Remediation
Run the following commands with neuroctl, replacing {service} with the affected service:
```neuroctl
kill_idle_connections {service}
increase_pool {service} size=200
```

## Verification
Connections fall below 80% of the pool size and timeouts stop.

## Rollback
Reduce the pool size back to 100 after the client-side leak is fixed.

## Escalation
Escalate to the application team to fix the connection leak.
