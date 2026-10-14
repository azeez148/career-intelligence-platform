# Platform architecture

The application is a modular monolith. Phase 3 adds durable, asynchronous career-source discovery to the identity, company, and preference modules from Phases 1–2. Further modules are created only as approved phases need them.

```mermaid
flowchart LR
    Browser[Angular browser application] --> Web[Nginx / Angular dev proxy]
    Web --> API[FastAPI /api/v1]
    API --> DB[(PostgreSQL 17)]
    Migration[Alembic one-shot service] --> DB
    Dispatcher[Outbox dispatcher] --> DB
    Dispatcher --> Redis[(Redis broker)]
    Redis --> Worker[Celery discovery worker]
    Worker --> DB
    Worker --> PublicWeb[Bounded public HTTP(S)]
```

`apps/api/app/main.py` composes the HTTP application. `core/` owns configuration, JSON logs, and error handling. `api/` owns HTTP contracts. `db/` owns SQLAlchemy metadata and async sessions. `modules/discovery/` owns scan state and pure discovery rules. `integrations/` owns the only outbound HTTP and Redis boundaries. `workers/` owns dispatch and task execution. Migrations remain explicit one-shot operations.

The browser uses relative `/api/v1` paths. Nginx forwards them in containers; the Angular development proxy forwards them during host development. The frontend build contains no deployment hostname or credentials. CORS is unnecessary for the supported same-origin route.

PostgreSQL is authoritative. Revision `0004_career_discovery` adds scans, candidates, career sources, a transactional outbox, and three permission contracts. Redis carries transient Celery messages and hostname-rate leases; it is never the source of user-visible state. Readiness verifies database connectivity and the deployed migration head. JWT identity, live sessions, database permissions, and owner-scoped queries protect operations; see [ADR 0004](../decisions/0004-career-discovery.md).

Starting or continuing a scan writes the scan and outbox row together. A dispatcher publishes deterministic task IDs. A worker claims a database lease and persists a terminal state or bounded retry. Duplicate deliveries are harmless, stale queued dispatches are republished, and expired running leases are recoverable. The Angular detail route polls PostgreSQL-backed status only while a scan is queued or running.

All discovery traffic passes through one address-pinning transport that validates every DNS answer, connection peer, and redirect; disables environment proxies; applies strict time and byte budgets; and respects robots rules. Static discovery identifies generic pages and Greenhouse, Lever, or Workday sources. A name-only guess requires explicit confirmation before it can enter the outbox.

Job extraction, browser rendering, normalization, matching, AI, schedules, notifications, resume handling, and application automation remain outside Phase 3.
