---
id: RB-010
incident_type: bad_deployment
services: api-gateway, auth-service, payment-service
severity: P1
---
# Faulty Release Deployed

## Symptoms
- Sharp increase in HTTP 500 errors immediately after a new version was deployed.
- New exceptions (for example NullPointerException) referencing the new version.
- Infrastructure metrics (CPU, memory, disk) look normal.

## Root Cause
The latest release contains a bug. The fastest safe fix is to roll back to the previous known-good version.

## Diagnosis Steps
1. Correlate the error spike with the deployment timestamp.
2. Confirm the errors mention code paths changed in the release.

## Remediation
Run the following commands with neuroctl, replacing {service} with the affected service:
```neuroctl
rollback_deployment {service}
```

## Verification
Error rate returns below 1% on the previous version.

## Rollback
Re-deploy the fixed version after the bug is resolved by developers.

## Escalation
Rollback is a HIGH-risk change and needs on-call approval. Notify the release owner.
