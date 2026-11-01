---
id: RB-002
incident_type: memory_leak
services: api-gateway, auth-service, payment-service
severity: P2
---
# Memory Leak in Application Process

## Symptoms
- Heap / resident memory steadily climbing to more than 90% without a traffic increase.
- Frequent full garbage collections, "GC overhead limit" warnings.
- java.lang.OutOfMemoryError or similar allocation failures in logs.

## Root Cause
An in-process cache or listener is retaining objects that are never released. Memory grows until the process
thrashes in garbage collection and starts failing requests.

## Diagnosis Steps
1. Compare memory growth with traffic; leak if memory rises while traffic is flat.
2. Look for OutOfMemoryError and GC overhead messages.
3. Note the last deployment time; capture a heap dump if possible for developers.

## Remediation
Run the following commands with neuroctl, replacing {service} with the affected service:
```neuroctl
restart_service {service}
```

## Verification
Memory drops back to baseline (around 50%) and error rate returns below 1%.

## Rollback
None required; a restart is non-destructive.

## Escalation
Open a bug for the owning team with the heap dump; escalate if leak returns within 1 hour.
