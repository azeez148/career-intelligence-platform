# Phase 1: authentication, profiles, and RBAC

Status: implemented and locally verified following explicit approval of [the plan](phase-1-plan.md); hosted CI verification pending. Phase 2 has not begun.

## Delivered behavior

Public registration, Argon2id password protection, login/logout, short-lived JWT cookies, rotating refresh cookies, replay detection, own-session listing/revocation, logout everywhere, current-user/profile APIs, database-driven RBAC, and Angular registration/login/profile/session screens. Backend permission checks enforce ownership and reflect database changes immediately. Existing foundation health/readiness behavior remains available.

## API contract

All paths below start with `/api/v1`. Responses are non-cacheable. Authentication cookies are not returned as JSON.

| Method/path | Input and result |
|---|---|
| GET `/auth/csrf` | 204, signed readable CSRF cookie |
| POST `/auth/register` | email, password, display_name; 201 public user; no automatic login |
| POST `/auth/login` | email/password; 200 `{user, access_expires_at}`, HttpOnly session cookies |
| POST `/auth/refresh` | JSON object and cookies; 200 `{access_expires_at}` plus rotated cookies |
| POST `/auth/logout` | JSON object; 204, current session revoked and cookies cleared |
| GET `/users/me` | 200 `{id,email,display_name,bio,permissions}` |
| PATCH `/users/me/profile` | display_name (required), bio (default empty); 200 public user |
| GET `/auth/sessions` | limit 1–100 (default 20), offset 0–100000; `{items,next_offset}`; only live owned sessions |
| DELETE `/auth/sessions/{uuid}` | 204 for own session; unknown/other owner's session 404 |
| POST `/auth/logout-all` | JSON object; 204, all current user's sessions revoked |

Errors retain `{error:{code,message,request_id}}`. Validation returns a sanitized generic 422 without input echoes. Domain errors distinguish unauthorized/invalid credentials, CSRF failure, forbidden permission, not found, duplicate email, throttling, and temporary saturation. Angular supplies field constraints and safe error messages.

## Files and design

- `apps/api/app/modules/{identity,users,authorization}/`: models, security helpers, services, contracts, routers, and permission dependencies.
- `app/db/models.py`, migration `0002_identity_profiles_rbac.py`: explicit metadata registry, nine tables, indexes, uniqueness, cascading FKs, default role/permission seed.
- API config, composition, logging/errors, routing, migration configuration, dependency lock, Docker command: security integration into existing foundation.
- `apps/web/src/app/auth/`, app shell/routes/config/styles, `e2e/auth.spec.ts`: accessible forms, own profile/session controls, guards, memory-only state, refresh coordination, logout broadcasts.
- Compose, Nginx, `.env.example`, CI: required independent secrets, exact origins, explicit proxy trust, ephemeral masked CI values, browser verification.
- Backend identity/security/regression tests and frontend unit/browser tests; operations, ADR, architecture, README, and test evidence.

See [ADR 0002](../decisions/0002-authentication-sessions-rbac.md) for alternatives and implementation adjustments, [authentication operations](../operations/authentication.md) for security/rollback behavior, and [test evidence](../testing/phase-1.md) for exact verification results.

## Limitations and next-phase boundary

Email ownership is unverified. Recovery, email changes, MFA, social identity, admin UI, scheduled session cleanup, and production TLS provisioning remain excluded. Strict replay rejection and fixed-window rate limits have documented usability/resource tradeoffs. This phase does not claim production release readiness.

Phase 2 can reuse authenticated users, database permission dependencies, and the modular monolith. No company or preference functionality is implemented. Stop after Phase 1 verification; a new explicit approval is required before Phase 2 work.
