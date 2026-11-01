---
id: RB-009
incident_type: queue_backlog
services: worker-queue
severity: P3
---
# Message Queue Backlog

## Symptoms
- Queue depth growing into tens of thousands of messages.
- Consumer lag increasing; jobs time out while waiting in the queue.
- Worker CPU high.

## Root Cause
The number of workers is too low for the incoming job rate, so messages accumulate faster than they are
processed.

## Diagnosis Steps
1. Compare the message arrival rate with the processing rate.
2. Confirm workers are processing (not stuck) by checking job completion logs.

## Remediation
Run the following commands with neuroctl, replacing {service} with the affected service:
```neuroctl
scale_service {service} replicas=6
```

## Verification
Queue depth starts falling and consumer lag returns to near zero.

## Rollback
Scale workers back down once the backlog is cleared.

## Escalation
Escalate if workers are stuck (no job completions) rather than slow.
