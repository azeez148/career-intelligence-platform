# ADR 0002: browser authentication and database authorization

Status: accepted for the approved Phase 1 scope.

## Decision

Use Argon2id (64 MiB, three iterations, one lane), short-lived HS256 JWT access cookies, and opaque rotating refresh cookies. JWTs contain identity/session identifiers and timestamps, not permissions. PostgreSQL validates active users, live sessions, and effective permissions on protected requests. Password work runs in bounded background threads; saturation returns 503.

Production cookies are host-only, Secure, HttpOnly, SameSite=Lax, Path=/, with `__Host-` names. An explicit development mode uses separate cookie names over local HTTP. Angular keeps public profile data in memory; credentials never enter browser storage. Signed session-bound double-submit CSRF tokens and exact Origin checks protect mutations, including login and registration. Angular's built-in XSRF support supplies the header on relative requests.

Refresh tokens have 256 bits of randomness; only SHA-256 digests persist. Rotation locks the session before the token, records consumption, and creates a replacement without extending the absolute seven-day expiry. Replay commits family revocation before returning 401. Logout uses the same session lock. A rejected refresh never clears a newer cookie. Web Locks coordinate tabs, with an access check after lock acquisition; each tab also coalesces refresh calls. BroadcastChannel sends login/logout events without tokens.

RBAC uses roles, permissions, and assignment tables. The database default-registration flag determines the new user's role. Seeded permission codes are API contracts, while role assignments remain data. Every session lookup/revocation is scoped to the authenticated owner. There is no public privilege-management endpoint or seeded administrator.

Fixed-window PostgreSQL counters provide atomic limits across workers without adding Redis. HMAC keys conceal account/IP identifiers. Failed-login reservations count immediately and successful logins refund the account counter. Expired counters are removed in batches of at most 100 with SKIP LOCKED. Lookup connections are released before independent rate-limit transactions to avoid exhausting the pool with waiting requests.

## Alternatives and consequences

- Bearer tokens in browser storage simplify CSRF but expose durable credentials to JavaScript; HttpOnly cookies fit this first-party application.
- Fully stateless JWT authorization cannot provide immediate revocation or permission changes. Database checks intentionally trade a query for those guarantees.
- Asymmetric JWT keys and an external identity provider add deployment complexity without a current multi-service verifier requirement. HS256 requires independent, random secrets and careful rotation.
- A refresh replay grace period improves lost-response recovery but weakens replay detection. Strict replay rejection can require signing in again after network loss or uncoordinated clients.
- Redis is deferred until its approved orchestration phase. Fixed windows permit bursts near boundaries and account throttling can be abused to inconvenience another account.
- A duplicate-email 409 helps registration UX but reveals registration status. Login errors remain generic. Email format validation does not prove ownership.

## Scope and implementation adjustments

Closely related cryptographic helpers share `identity/security.py`; existing services and dependencies avoid empty abstractions. Angular's small auth slice lives under `src/app/auth/` rather than separate core/features trees. Tests are grouped in `test_identity.py`, `test_security.py`, and `auth.spec.ts`. Counter window start is encoded into the HMAC bucket key; expiry is indexed, so no redundant window column is stored. Profile PATCH replaces the editable display-name/bio pair. These keep the approved behavior while reducing file/abstraction overhead.

No company, preference, discovery, AI, password recovery, email verification, MFA, social login, or administrative UI is implemented.
