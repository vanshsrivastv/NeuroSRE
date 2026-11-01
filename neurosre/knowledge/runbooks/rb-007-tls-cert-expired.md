---
id: RB-007
incident_type: tls_cert_expired
services: api-gateway
severity: P1
---
# Expired TLS Certificate

## Symptoms
- TLS handshake failures: "x509: certificate has expired".
- Clients report SSL_ERROR_EXPIRED_CERT_ALERT.
- High error rate on the gateway while backend services are healthy.

## Root Cause
The public TLS certificate passed its expiry date because automatic renewal failed.

## Diagnosis Steps
1. Check the certificate expiry date on the gateway.
2. Confirm backend services are healthy (the problem is only at the edge).

## Remediation
Run the following commands with neuroctl, replacing {service} with the affected service:
```neuroctl
renew_certificate {service}
```

## Verification
TLS handshakes succeed and the gateway error rate returns below 1%.

## Rollback
Not applicable.

## Escalation
Escalate if renewal fails (for example DNS validation errors).
