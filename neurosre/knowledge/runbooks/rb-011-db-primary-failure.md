---
id: RB-011
incident_type: db_primary_failure
services: orders-db
severity: P1
---
# Database Primary Node Failure

## Symptoms
- Primary database node unreachable ("no route to host", connection timed out).
- All writes failing; error rate 100%.
- Replica healthy with low replication lag.

## Root Cause
The primary database host failed. The healthy replica must be promoted to primary to restore writes.

## Diagnosis Steps
1. Confirm the primary is unreachable from more than one client.
2. Confirm the replica is healthy and replication lag is small (less than 1 s) to avoid data loss.

## Remediation
Run the following commands with neuroctl, replacing {service} with the affected service:
```neuroctl
failover_database {service}
```

## Verification
Writes succeed against the new primary and error rate returns below 1%.

## Rollback
Rebuild the failed node as a new replica.

## Escalation
Failover is a HIGH-risk change and needs on-call approval. Never fail over if replication lag is large.
