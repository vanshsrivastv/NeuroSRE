---
id: RB-008
incident_type: cache_failure
services: redis-cache
severity: P2
---
# Cache Server Down

## Symptoms
- "Connection refused" when connecting to redis-cache:6379.
- Applications fall back to the database, which increases latency.
- redis-server terminated unexpectedly.

## Root Cause
The cache process crashed. Applications keep working through the database but slower; prolonged outage will
overload the database.

## Diagnosis Steps
1. Confirm the cache process is not running.
2. Check database load, since it rises while the cache is down.

## Remediation
Run the following commands with neuroctl, replacing {service} with the affected service:
```neuroctl
restart_service {service}
```

## Verification
Cache accepts connections and hit rate starts recovering.

## Rollback
Not applicable.

## Escalation
If the cache crashes repeatedly, escalate and check for memory exhaustion.
