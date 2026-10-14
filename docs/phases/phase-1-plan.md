# Phase 1 implementation plan: authentication, profiles, and RBAC

Status: approved by the user; implementation in progress.

## Starting evidence and scope

Phase 0 implementation commit `5d2b908` passed [hosted CI](https://github.com/azeez148/career-intelligence-platform/actions/runs/38544334866). The inspected repository has an application factory, async database/session dependencies, explicit migrations, JSON error handling, Angular Router/HttpClient, and working container/test infrastructure. It has no identity tables, password/JWT libraries, authentication endpoints, route guards, or profile forms.

Reuse these seams. Extend the modular monolith with identity, users, and authorization modules. Deliver public registration, login/logout, JWT access authentication, rotating refresh tokens, session revocation, current user, editable own profile, database-driven RBAC, and protected Angular screens.

Excluded: company/preferences/job functionality, discovery, AI, social login, MFA, password recovery, email delivery/verification, administrative dashboard, public role-management APIs, and scheduled tasks. Email ownership will not be claimed as verified. Self-service email changes are excluded until a verification flow is separately approved.

## Authentication and session design

### Credentials

- Add compatible, exactly pinned `argon2-cffi`, `PyJWT`, and `email-validator`; verify Python 3.13 and Alpine wheels and rerun dependency/image audits before accepting the lock changes.
- Hash passwords with Argon2id using per-password salts. Start with 64 MiB memory, 3 iterations, parallelism 1, then benchmark within deployment limits without dropping below current OWASP minima.
- Run password hashing/verification outside the async event loop with bounded concurrency. Reject oversized inputs before hashing. Proposed policy: 15–128 Unicode characters, no silent trimming or truncation, allow spaces and paste; no arbitrary character-class requirements.
- Rehash on successful login when the configured work factor changes. Use dummy-hash verification for nonexistent accounts and a generic invalid-credentials response.
- Validate email format without external DNS calls. Treat login emails as case-insensitive account identifiers; store a normalized canonical value under a database unique constraint. Do not strip provider-specific dots or plus tags.
- Registration assigns only the ordinary member role. Input schemas forbid unexpected fields, including role, permission, activation, and ownership fields. No default administrator or default password.

### JWT and browser storage

- Access JWT lifetime: configurable, proposed 10 minutes. Validate a fixed allowed algorithm, signature, issuer, audience, subject, session ID, issued-at, and expiry. Do not accept an algorithm chosen by the token or place roles/permissions in the JWT.
- Use HS256 with a required high-entropy signing secret for this single backend deployment. Separate CSRF/rate-limit secrets; no checked-in development fallback. Document that signing-key replacement invalidates existing access tokens.
- Store access JWT and opaque refresh token in host-only HttpOnly cookies. Production cookies require Secure and SameSite=Lax; use `__Host-` names with Path=/ and no Domain in production. Local HTTP requires an explicit development configuration with separate unprefixed names.
- JavaScript does not receive tokens in response bodies or browser storage. The Angular app stores only current-user/session display state in memory and restores it by calling the API.
- Protected backend requests verify that the user is active and the referenced session is unexpired and unrevoked in PostgreSQL. This makes logout/session revocation effective for existing access JWTs immediately and makes permission changes effective on the next request.
- Authentication/session responses use `Cache-Control: no-store`. Preserve public health endpoints.

### Rotation, replay, and concurrency

- Generate refresh tokens using at least 256 bits of cryptographic randomness. Store only SHA-256 token digests, never raw tokens; a fast hash is appropriate here because tokens have high entropy, unlike passwords.
- Proposed absolute session/refresh lifetime: 7 days. Rotation never extends that absolute expiry indefinitely.
- Retain consumed token digests until the session expires so reuse remains detectable. Lock the session/token rows and consume/replace the token in one transaction.
- Reuse of a consumed refresh token revokes its whole session/token family. Ensure revocation commits before returning 401; do not roll it back by raising an exception inside the transaction.
- Logout and rotation serialize on the same session row. A concurrent refresh must not resurrect a revoked session. A failed refresh does not overwrite a newer successful cookie with a stale cookie.
- Angular uses a single shared refresh operation per tab and coordinates refresh between same-origin tabs with Web Locks. Retry a protected request at most once after successful refresh; do not recurse through authentication endpoints or refresh on 403. Notify other tabs of logout through BroadcastChannel without transmitting tokens.
- Strict replay rejection means a lost refresh response or an uncoordinated client may require signing in again. Document this tradeoff; do not add a replay grace window that silently weakens detection.

### CSRF and resource limits

- Cookie authentication requires CSRF protection. Provide a bootstrap endpoint that sets a signed double-submit CSRF cookie; Angular sends its value in `X-XSRF-TOKEN` on state-changing relative API requests.
- Verify signature, header/cookie equality, and a configured exact Origin allowlist. Bind the token to the session after login and rotate it at authentication boundaries. Pre-authentication tokens protect login/registration from login-CSRF. Require JSON for authentication mutations; reject missing/foreign origin on supported browser mutation flows.
- Do not rely on SameSite alone. No wildcard credentialed CORS. Trust forwarded client addresses only from explicitly configured proxy peers; overwrite rather than relay user-supplied forwarding headers at the local Nginx boundary.
- Add atomic PostgreSQL-backed authentication rate limits keyed by a keyed digest of client IP and normalized account identifier. Proposed defaults: 5 failed login attempts/account/15 minutes, 30 login attempts/IP/15 minutes, 5 registrations/IP/hour, 30 refreshes/session/minute; configurable and tested with an injected clock. Return 429 and Retry-After.
- Use fixed-window counters with bounded, incremental expiry cleanup during auth requests; document counter cardinality and account-throttling denial-of-service tradeoffs. This gives consistent limits across API processes without introducing Redis ahead of Phase 3.
- Record allowlisted security events (login outcome, logout, token reuse, session revocation, permission denial) with request/user/session identifiers where available. Do not log passwords, email addresses, JWTs, token digests, CSRF values, or raw request bodies.

## Data model and migration

Create `0002_identity_profiles_rbac.py` after the existing foundation revision.

| Table | Purpose and important constraints |
|---|---|
| `users` | UUID PK, canonical unique email, password hash, active flag, UTC creation/update times |
| `user_profiles` | One-to-one user FK/PK; bounded display name and optional bio; no skills/location lists or preference data |
| `roles` | UUID PK, unique stable code, description, default-registration flag; at most one default role |
| `permissions` | UUID PK, unique stable permission code and description |
| `user_roles` | User/role FKs, composite uniqueness |
| `role_permissions` | Role/permission FKs, composite uniqueness |
| `auth_sessions` | UUID PK, user FK, created/absolute-expiry/revoked timestamps; one row per browser login |
| `refresh_tokens` | Unique token digest, session FK, issued/expiry/consumed timestamps and replacement linkage |
| `auth_rate_limits` | Keyed subject digest, action, window start, atomic counter, expiry; unique bucket key and cleanup index |

Use explicit indexes for authentication lookups and user/session ownership queries. Seed a member role and explicit permissions such as `profile:read:self`, `profile:update:self`, `sessions:read:self`, and `sessions:revoke:self`. Permission codes are application contracts; role membership and permission assignments are database state, not scattered controller role-name checks. The default role is selected from database configuration, with registration failing safely if configuration is absent.

Alembic must import the registered models for metadata discovery. Test upgrade from Phase 0, repeated upgrade, downgrade in a disposable database, and re-upgrade. The Phase 1 downgrade deletes identity data and is documented as destructive; do not run it against a real user database automatically.

## Backend authorization and API contracts

Reuse `get_session` and the existing error envelope. Thin routers invoke focused services that own transaction boundaries. Add reusable current-user and `require_permission(code)` dependencies. Every profile/session query also scopes by the authenticated user ID; an Angular guard never substitutes for backend authorization.

| Method and route (under `/api/v1`) | Contract |
|---|---|
| `GET /auth/csrf` | 204; sets/refreshes readable signed CSRF cookie |
| `POST /auth/register` | Email, password, display name; 201 with public user/profile data; no automatic login |
| `POST /auth/login` | Email/password; 200 with public user/permissions and expiry metadata; sets auth cookies |
| `POST /auth/refresh` | Rotates refresh token; 200 with expiry metadata; sets new cookies |
| `POST /auth/logout` | Idempotent 204; revokes current session and clears cookies |
| `GET /users/me` | 200 with own user/profile/effective permissions; never returns hashes/token internals |
| `PATCH /users/me/profile` | Update own display name/bio only; 200 with updated profile |
| `GET /auth/sessions` | Own sessions only, bounded pagination; no raw user-agent/IP or tokens |
| `DELETE /auth/sessions/{id}` | Revoke an owned session; 204; clear cookies when revoking current session |
| `POST /auth/logout-all` | 204; revoke all sessions for current user and clear current cookies |

Errors: 401 invalid/expired/revoked authentication; 403 permission or CSRF failure; 404 unknown/not-owned session; 409 duplicate normalized email; 422 invalid input; 429 throttled requests with Retry-After. Duplicate-email 409 intentionally discloses account existence; document this registration UX tradeoff. Login still returns a generic error. Add stable domain error codes and safe field-validation information without echoing sensitive input, preserving Phase 0's sanitized unexpected-error behavior.

## Files and frontend work

Create backend modules only as required:

- `apps/api/app/modules/identity/{models,schemas,passwords,tokens,csrf,rate_limits,service,dependencies,router}.py`
- `apps/api/app/modules/users/{models,schemas,service,router}.py`
- `apps/api/app/modules/authorization/{models,service,dependencies}.py`
- `apps/api/app/db/models.py` as explicit model registration for Alembic.
- `apps/api/migrations/versions/0002_identity_profiles_rbac.py`.
- Focused unit/integration tests under `apps/api/tests/identity/`, `users/`, and `authorization/`.

Modify backend composition/configuration/error handling, `migrations/env.py`, dependency manifests/locks, and existing migration/health tests. In particular, replace Phase 0's permanent assumptions of one `0001_foundation` head and no application tables with assertions appropriate to the new migration, retaining health/outage regression coverage.

Create Angular code under:

- `apps/web/src/app/core/auth/`: typed auth service, in-memory auth state, refresh coordinator/interceptor, authenticated/guest/permission guards, and tests.
- `apps/web/src/app/features/auth/`: standalone login and registration pages using Reactive Forms.
- `apps/web/src/app/features/profile/`: own profile editor and session management page, with tests.
- `apps/web/e2e/auth.spec.ts` and `profile-sessions.spec.ts`.

Modify app configuration/routes/shell. Proposed routes: `/login`, `/register`, `/profile`, `/sessions`; retain the foundation page. Show useful loading/validation/401/403/429 states, accessible labels, correct password autocomplete attributes, logout controls, and safe internal return navigation. Password fields never repopulate from persisted state.

Update `.env.example`, Compose environment wiring, Nginx proxy/header configuration, and `.github/workflows/ci.yml`. Generate ephemeral auth secrets in CI, mask them, and pass them to the isolated stack. Maintain existing checks and add authentication browser journeys. No secret values enter Git or frontend bundles.

## Test and acceptance matrix

| Area | Required proof |
|---|---|
| Registration | Invalid/oversized inputs, duplicate/case-equivalent email, concurrent duplicate requests, privilege-field rejection, member-only assignment |
| Password protection | Argon2id hashes, distinct salts, correct/wrong passwords, work-factor rehash, no plaintext persistence/logs, bounded hashing |
| JWT validation | Bad signature, wrong algorithm/issuer/audience, missing claims, expired token, invalid subject/session |
| Refresh and revocation | Rotation invalidates old token; replay revokes family; expiry; logout/logout-all; concurrent refresh; refresh-vs-logout race; revocation persists after 401 |
| CSRF/cookies | Secure/HttpOnly/SameSite/host scoping, explicit local dev mode, missing/tampered/foreign-origin tokens, pre-login protection, no auth tokens in browser storage |
| RBAC and isolation | Permission denied/allowed; DB permission change applies with existing JWT; disabled user; no self-escalation; another user's profile/session is inaccessible |
| Rate limits | Cross-session atomic counter behavior, thresholds/reset/cleanup, 429 Retry-After, forwarded-address spoof resistance |
| Angular | State restoration, guards, one refresh for concurrent requests, no refresh loop, cross-tab coordination, safe return URL, accessible forms and errors |
| Playwright | Register/login/reload/profile edit/logout; current/all-session revocation; unauthorized navigation; expired-access refresh; two users isolated |
| Migration/regression | Phase 0 → Phase 1 upgrade/downgrade/re-upgrade, existing health/outage tests, container startup, strict builds/lint/types |
| Security and CI | Dependency audits, secret scan, all runtime scans, and successful hosted CI for the Phase 1 implementation commit |

Use real PostgreSQL for uniqueness, transaction-locking, rotation races, permissions, and isolation. Use deterministic clocks for expiry/rate tests instead of long sleeps. Mock cryptographic boundaries only where the test is not claiming cryptographic correctness. Browser success paths use the real backend/database.

Acceptance: all master-plan Phase 1 features are present; protected operations fail closed; revocation and replay defenses work; no token/password exposure; no cross-user access; migrated containers and all applicable local/hosted gates pass; documentation records exact outcomes and limitations; no Phase 2 code.

## Documentation, sequence, and stop condition

After approval, implement incrementally: schema/RBAC → credentials/session services → CSRF/authorization/routes → Angular flows → regression/security/hosted CI → completion documentation. Commit logical increments and fix failing gates before declaring completion.

Create `docs/decisions/0002-authentication-sessions-rbac.md`, `docs/phases/phase-1.md`, `docs/testing/phase-1.md`, and `docs/operations/authentication.md`. Update architecture/README/API contracts and document configuration, key rotation effects, profile ownership, session races, RBAC seed changes, rate-limit tradeoffs, migrations, and excluded functionality.

This document is the reviewable plan, not approval to implement. Wait for explicit approval, then implement Phase 1 only and stop before Phase 2.

## Security references reviewed

- [OWASP password storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): Argon2id and work factors.
- [OWASP CSRF prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): signed double-submit tokens, origin checks, and SameSite as defense in depth.
- [RFC 9700, section 4.14](https://www.rfc-editor.org/rfc/rfc9700.html#section-4.14): refresh-token rotation and replay detection principles. This application is not implementing an OAuth authorization server.
