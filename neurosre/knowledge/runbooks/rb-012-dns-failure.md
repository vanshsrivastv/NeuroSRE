---
id: RB-012
incident_type: dns_failure
services: api-gateway, auth-service, payment-service
severity: P2
---
# Internal DNS Resolution Failure

## Symptoms
- Errors such as "getaddrinfo ENOTFOUND" or "Temporary failure in name resolution".
- Calls to internal hostnames (*.internal) fail while the target services are healthy.
- Stale DNS cache entries.

## Root Cause
The service's local DNS resolver cache holds stale or negative entries after an internal DNS change.

## Diagnosis Steps
1. Confirm the target services are healthy, which rules out a real outage.
2. Check whether resolution fails only from this service.

## Remediation
Run the following commands with neuroctl, replacing {service} with the affected service:
```neuroctl
flush_dns_cache {service}
```

## Verification
Internal hostnames resolve and the error rate returns to baseline.

## Rollback
Not applicable.

## Escalation
Escalate to the platform team if resolution fails cluster-wide.
