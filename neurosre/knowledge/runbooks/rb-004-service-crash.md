---
id: RB-004
incident_type: service_crash
services: api-gateway, auth-service, payment-service
severity: P1
---
# Service Crash / CrashLoopBackOff

## Symptoms
- Service status DOWN, health checks failing with "connection refused".
- Process exited with a non-zero code (for example 139 segmentation fault).
- Container restarting repeatedly (CrashLoopBackOff), error rate 100%.

## Root Cause
The process crashed because of a transient fault (bad request, native library crash) and the container did not
come back cleanly.

## Diagnosis Steps
1. Check the exit code and the last log lines before the crash.
2. Check whether a deployment happened recently; if yes see RB-010 (Faulty Release).

## Remediation
Run the following commands with neuroctl, replacing {service} with the affected service:
```neuroctl
restart_service {service}
```

## Verification
Health check returns 200 and the service status is HEALTHY.

## Rollback
Not applicable.

## Escalation
If the service crashes again within 10 minutes, escalate to the owning team.
