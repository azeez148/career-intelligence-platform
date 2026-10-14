# Foundation architecture

The application is a modular monolith. Phase 1 adds identity, users/profiles, and authorization modules to the completed foundation. Further modules are created only as approved phases need them.

```mermaid
flowchart LR
    Browser[Angular browser application] --> Web[Nginx / Angular dev proxy]
    Web --> API[FastAPI /api/v1]
    API --> DB[(PostgreSQL 17)]
    Migration[Alembic one-shot service] --> DB
```

`apps/api/app/main.py` composes the application and owns startup/shutdown. `core/` owns configuration, JSON logs, and error handling. `api/` owns HTTP contracts. `db/` owns SQLAlchemy metadata, async connection pools, and session lifecycles. Migrations are separate explicit operations. No connection is opened at module import time, and no schema is created by application startup.

The browser uses a relative `/api/v1` path. Nginx forwards it in containers; the Angular development proxy forwards it during host development. The frontend build therefore contains no deployment hostname or credentials. CORS is unnecessary for the supported same-origin route.

PostgreSQL is authoritative. Revision `0002_identity_profiles_rbac` follows the empty foundation revision and adds nine identity/RBAC tables. Readiness verifies both connectivity and the deployed migration head, so an unmigrated database cannot appear ready. JWT identity, live session state, effective database permissions, and owner-scoped queries protect account operations; see [ADR 0002](../decisions/0002-authentication-sessions-rbac.md).

The API remains live during database outages. Connection acquisition and readiness have bounded deadlines. Pool pre-ping detects dead connections; shutdown disposes the pool. Each future request session receives its own async SQLAlchemy session; future services must own transaction boundaries explicitly.

The foundation page retains loading, connected, and unavailable states plus retry. Account routes add registration, login, profile editing, and session management. HttpOnly cookies hold credentials; public account data stays in memory. No scheduled polling, business dashboard, scanning, AI, or matching is present.

Future boundaries from the master plan remain identity/users/RBAC, preferences, companies, discovery, extraction, normalization/jobs, matching, integrations, and orchestration. Redis/Celery and Python Playwright belong to their later phases, not this runtime.
