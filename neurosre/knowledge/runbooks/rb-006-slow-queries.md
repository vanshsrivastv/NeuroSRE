---
id: RB-006
incident_type: slow_queries
services: orders-db
severity: P2
---
# Long-Running Queries Blocking the Database

## Symptoms
- Slow query log shows queries taking many seconds with sequential (full table) scans.
- Lock wait timeouts and statement timeouts.
- High database CPU and latency.

## Root Cause
An unindexed ad-hoc or reporting query scans a large table and holds locks, blocking normal traffic.

## Diagnosis Steps
1. List queries running longer than 30 seconds.
2. Confirm they are reporting / ad-hoc queries, not migrations.

## Remediation
Run the following commands with neuroctl, replacing {service} with the affected service:
```neuroctl
kill_long_queries {service}
```

## Verification
Database latency returns below 50 ms and lock waits stop.

## Rollback
Not applicable.

## Escalation
Ask the data team to add the missing index; escalate if a schema migration is running.
