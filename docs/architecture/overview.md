# Platform architecture

The application is a modular monolith. Phase 3 added durable, asynchronous career-source discovery; Phase 4 adds job extraction, normalization, and a job explorer on top of it. Further modules are created only as approved phases need them.

```mermaid
flowchart LR
    Browser[Angular browser application] --> Web[Nginx / Angular dev proxy]
    Web --> API[FastAPI /api/v1]
    API --> DB[(PostgreSQL 17)]
    Migration[Alembic one-shot service] --> DB
    Dispatcher[Outbox dispatcher] --> DB
    Dispatcher --> Redis[(Redis broker)]
    Redis -->|discovery, extraction| Worker[Celery worker]
    Redis -->|extraction-browser| BrowserWorker[Browser worker: Chromium headless shell]
    Worker --> DB
    BrowserWorker --> DB
    Worker --> SafeHTTP[SafeHttpClient: pinned DNS, redirects, robots, budgets]
    BrowserWorker -->|every intercepted request| SafeHTTP
    SafeHTTP --> PublicWeb[Public HTTP(S)]
```

## Code layout

| Path under `apps/api/app/` | Owns |
|---|---|
| `main.py` | Composing the HTTP application |
| `core/` | Configuration, JSON logs, error handling |
| `api/` | HTTP contracts |
| `db/` | SQLAlchemy metadata and async sessions |
| `modules/discovery/` | Scan state and discovery rules |
| `modules/extraction/` | Runs, strategy order, persistence, and the pure strategy parsers |
| `modules/jobs/` | The normalized job model, normalization rules, and read API |
| `integrations/` | The only outbound boundaries: HTTP, robots, browser, Redis |
| `workers/` | Dispatch and task execution |

Migrations remain explicit one-shot operations.

## Requests and data

The browser uses relative `/api/v1` paths. Nginx forwards them in containers, and the Angular development proxy forwards them during host development. The frontend build contains no deployment hostname or credentials.

PostgreSQL is authoritative. Revision `0005_job_extraction` adds extraction runs and their outbox, normalized jobs, run-to-job observations, and two permission contracts. Redis carries only transient Celery messages and hostname-rate leases. JWT identity, live sessions, database permissions, and owner-scoped queries protect every operation; see [ADR 0004](../decisions/0004-career-discovery.md) and [ADR 0005](../decisions/0005-job-extraction.md).

## Asynchronous work

Scans and extraction runs each write their state row and outbox row in one transaction. The dispatcher publishes deterministic task IDs per kind and routes them to a queue:

- `discovery.run` → `discovery`
- `extraction.run` → `extraction`
- `extraction.browser` → `extraction-browser`

Workers claim database leases and persist a terminal state or a bounded retry. Duplicate deliveries are harmless, and expired leases are recoverable. When discovery succeeds, it queues one extraction run per source.

## Extraction

Extraction tries strategies in a fixed order and stops at the first that yields jobs:

1. Official Greenhouse and Lever APIs.
2. schema.org JSON-LD.
3. Generic static listings.
4. Browser rendering, only for pages that look script-rendered.

Jobs are normalized without invented values, deduplicated within and across sources, linked to the runs that saw them, and closed only after complete runs. The Angular scan and job pages poll PostgreSQL-backed status only while work is active.

## Outbound networking

All outbound traffic, including every browser sub-request, passes through one address-pinning transport. It validates every DNS answer, connection peer, and redirect; ignores environment proxies; applies time, byte, and response budgets; and respects robots rules. Chromium runs in its own non-root, read-only Debian image behind a dead proxy, so a request that escapes interception fails closed. A test-only hostname allowlist exists for the isolated stack, and settings reject it in production.

## Out of scope

Matching, AI, schedules, notifications, saved jobs, resume handling, and application automation remain outside Phase 4.
