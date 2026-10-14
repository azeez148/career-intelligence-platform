# Authentication operations

## Configuration

Copy `.env.example` to `.env`. Generate **three independent** secrets with `python -c "import secrets; print(secrets.token_urlsafe(48))"` and set `JWT_SECRET`, `CSRF_SECRET`, and `RATE_LIMIT_SECRET`. Each must contain at least 32 bytes. Do not print deployed values in logs or commit them. Generate a separate URL-safe database password.

`ENVIRONMENT` defaults to `production`: HTTPS origins and Secure cookies are mandatory. Use `development` explicitly only for local HTTP. `ALLOWED_ORIGINS` is a JSON array of exact scheme/host/port values, without trailing slashes; keep the browser and API behind the same origin. No credentialed cross-origin flow is provided. Production TLS must terminate at a configured edge; the local Compose HTTP listener is not a production TLS deployment.

`TRUSTED_PROXY_CIDRS` defaults to `[]`. Configure only the actual trusted edge address/subnet. The local example trusts Docker's 172.16/12 private range for development; narrow it for deployment. Nginx overwrites X-Forwarded-For with its socket peer, and Uvicorn proxy parsing is disabled. A production proxy chain needs explicit review: the current single-edge contract accepts one overwritten address, not a forwarded chain.

| Setting | Default |
|---|---|
| `ACCESS_TOKEN_SECONDS` | 600 |
| `SESSION_SECONDS` | 604800 (absolute, never extended by refresh) |
| `CSRF_SECONDS` | 86400 |
| `JWT_ISSUER`, `JWT_AUDIENCE` | `career-intelligence`, `career-web` |
| `PASSWORD_WORKERS` | 2 per API process; at most about 128 MiB of simultaneous Argon2 working memory |
| `LOGIN_ACCOUNT_LIMIT` | 5 failed/reserved attempts per 15-minute fixed window |
| `LOGIN_IP_LIMIT` | 30 attempts per 15 minutes |
| `REGISTRATION_IP_LIMIT` | 5 attempts per hour |
| `REFRESH_SESSION_LIMIT` | 30 attempts per minute |

These variables can be exported for host execution. Compose wires the required secrets/origins/proxy settings; add an explicit reviewed Compose override for optional tuning. Tests generate their own secrets. The disposable browser stack raises only its registration limit to 100 to permit repeated test users.

## Keys and revocation

Replacing the JWT secret invalidates existing access JWTs; valid refresh sessions can obtain new access cookies. To sign out everyone, revoke all live `auth_sessions` in an audited database transaction as well. Replacing the CSRF secret invalidates outstanding CSRF cookies; clients fetch a new bootstrap token. Replacing the rate-limit secret starts new buckets and resets effective counters. Deploy a consistent key set to all API instances.

Session revocation and disabling users affect existing access JWTs on the next request. Requests already authorized before revocation may finish. Role/permission changes similarly apply on the next backend authorization check; cached browser menus are advisory. Manage role assignments through reviewed database operations until a separately approved administrative workflow exists. Never grant privilege based on a frontend guard.

Consumed refresh digests remain available for replay detection for the session lifetime. Periodically remove **expired** auth sessions in bounded database batches; foreign-key cascades remove their refresh records. Do not delete consumed refresh rows belonging to live sessions. There is no scheduler in Phase 1. Rate-limit rows clean themselves incrementally during auth requests; monitor table cardinality and pool saturation under distributed abusive traffic.

## Browser behavior and troubleshooting

- Registration does not sign in automatically. Passwords are 15–128 Unicode characters and are not trimmed. Emails are normalized and case-insensitive; dots/plus tags are not rewritten.
- `GET /auth/csrf` bootstraps the signed readable `XSRF-TOKEN`; state-changing JSON requests need its matching `X-XSRF-TOKEN` header and an allowed Origin.
- 401 means authentication failed/expired/revoked; 403 means CSRF or permission denial; 429 includes Retry-After; 503 can indicate database/unavailable hashing capacity.
- Supported modern browsers use Web Locks and BroadcastChannel. Without Web Locks, per-tab coalescing still works but simultaneous tab refreshes can trigger strict replay revocation. Lost refresh responses can also require a fresh login. No replay grace period is provided.
- A logout failure leaves the session active and displays an error, allowing retry. Clearing local UI alone must not be presented as successful server revocation.
- Security logs contain event names and allowlisted user/session IDs, never raw email/IP/password/token values. Application request completion logs supply request IDs. Authentication service events currently correlate by user/session IDs rather than carrying a request ID on every event.

## Migration safety

Revision `0002_identity_profiles_rbac` creates nine identity/RBAC tables and seeds the default member role and four self-service permissions. Upgrade from the existing Phase 0 revision before starting the new API. Alembic needs only database configuration, not signing secrets.

**Downgrading to Phase 0 deletes all user, profile, role, session, refresh, and auth-rate data.** It is tested only on disposable databases. Back up a real database and review data loss before any downgrade; prefer restoring a compatible application version with a reviewed forward fix. Never run test-stack volume cleanup against a development or deployed project.
