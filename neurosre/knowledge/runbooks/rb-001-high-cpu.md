---
id: RB-001
incident_type: high_cpu
services: api-gateway, auth-service, payment-service
severity: P2
---
# High CPU Utilisation from Traffic Spike

## Symptoms
- CPU usage above 90% on most replicas; container CPU throttling messages.
- p99 latency several times higher than normal; request queue growing.
- Upstream request timeouts while memory and disk look normal.

## Root Cause
A sudden increase in incoming requests (marketing campaign, retry storm or bot traffic) exceeds the capacity
of the current replica count. The service is healthy but under-provisioned.

## Diagnosis Steps
1. Confirm CPU is high on all replicas, not just one (one hot replica suggests a stuck thread instead).
2. Check requests per second against the normal baseline.
3. Make sure memory is normal, which rules out a memory leak causing GC pressure.

## Remediation
Run the following commands with neuroctl, replacing {service} with the affected service:
```neuroctl
scale_service {service} replicas=5
```

## Verification
CPU falls below 70% and p99 latency returns to baseline within 2 minutes of scaling.

## Rollback
Scale back to the original replica count once traffic normalises.

## Escalation
Escalate if CPU stays above 90% after scaling to 8 replicas, as it may be a code-level regression.
