---
id: RB-003
incident_type: disk_full
services: api-gateway, auth-service, payment-service, orders-db
severity: P1
---
# Disk Full due to Log Growth

## Symptoms
- Filesystem usage at 97-100%.
- Errors such as "No space left on device" or ENOSPC when writing files.
- Writes failing while CPU and memory are normal.

## Root Cause
Application logs and temporary files have filled the volume because log rotation did not run or debug logging
was left enabled.

## Diagnosis Steps
1. Check which mount is full (usually /var/log or /tmp).
2. Identify the largest files; confirm they are logs or temporary files, never data files.

## Remediation
Run the following commands with neuroctl, replacing {service} with the affected service:
```neuroctl
rotate_logs {service}
clear_tmp {service}
```

## Verification
Disk usage drops below 70% and write errors stop.

## Rollback
Not applicable; rotated logs are archived, not deleted.

## Escalation
Escalate if data files (not logs) are filling the disk; never delete data files automatically.
