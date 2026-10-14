# Phase 0: Project foundation

Implementation date: 2026-10-14. The user explicitly approved the repository audit and Phase 0 plan before implementation. No Phase 1 work is authorized or implemented.

## Scope delivered

- FastAPI application factory and lifecycle, validated environment settings, async SQLAlchemy engine/session support, structured JSON logs, request IDs, and global sanitized error responses.
- Independent liveness and database/schema-aware readiness endpoints.
- PostgreSQL 17, explicit Alembic migrations, and an empty foundation revision.
- Angular 22 standalone application, strict TypeScript/templates, Router, SCSS, typed HTTP service, loading/unavailable/ready UI, and retry.
- Dockerfiles, health-ordered Compose startup, optional host-development database port, and an isolated test override.
- pytest/pytest-asyncio, real PostgreSQL Testcontainers integration, Angular unit tests, Playwright smoke tests, Ruff, mypy, ESLint, dependency audits, and container/secret checks.
- GitHub Actions workflow with pinned action commits, locked installations, bounded jobs, minimal permissions, test artifacts, and cleanup.
- Architecture, decision record, operations, and verification documentation.

## API contracts

| Route | Result |
|---|---|
| `GET /api/v1/health/live` | 200, `{"status":"ok"}`; never accesses the database |
| `GET /api/v1/health/ready` | 200, `{"status":"ready","checks":{"database":"ok","schema":"ok"}}` |
| Ready with database failure/timeout | 503, `{"status":"not_ready","checks":{"database":"unavailable","schema":"unknown"}}` |
| Ready with missing/outdated revision | 503, `{"status":"not_ready","checks":{"database":"ok","schema":"mismatch"}}` |

Readiness sends `Cache-Control: no-store`. Responses carry a generated `X-Request-ID`. HTTP, request-validation, and unexpected failures use `{"error":{"code":"...","message":"...","request_id":"..."}}` with appropriate status (including 404/422/500). Diagnostic responses do not expose connection strings, raw validation input, or exception details. `/docs` and `/openapi.json` expose the documented local API.

## Database and business logic

Alembic revision `0001_foundation` introduces no business tables. `alembic_version` is the only migration bookkeeping table. Upgrade/downgrade/re-upgrade are tested on disposable PostgreSQL. Sessions are dependency-managed; no business transaction logic exists yet.

Readiness executes `SELECT 1`, checks for migration bookkeeping, and compares the recorded revisions with migration heads shipped in the application. Failure is bounded and sanitized. Liveness deliberately remains successful during a database outage. The frontend retries only on user action and cancels subscriptions when destroyed.

## File inventory

| Location | Created / changed content |
|---|---|
| Root | `.gitignore`, `.gitattributes`, `.editorconfig`, `.dockerignore`, `.env.example`, `README.md`, `compose.yaml`, `compose.dev.yaml`, `compose.test.yaml` |
| `apps/api/` | `pyproject.toml`, `uv.lock`, `Dockerfile`, `.dockerignore`, `alembic.ini` |
| `apps/api/app/` | Application factory, core configuration/errors/logging, API router/health, DB base/session, package initializers |
| `apps/api/migrations/` | Async Alembic environment, revision template, `0001_foundation` |
| `apps/api/tests/` | Shared client fixture, foundation unit tests, PostgreSQL integration tests |
| `apps/web/` | Angular workspace, exact package manifest/lock, strict tsconfigs, ESLint, formatting/editor configuration, Node version, proxy, Docker files, README, Playwright config |
| `apps/web/src/` | Bootstrap, HTML/styles, app shell/config/routes, foundation component, typed health service, unit tests |
| `apps/web/e2e/` | Real-stack smoke and outage/retry tests |
| `infrastructure/nginx/` | SPA routing and API proxy configuration |
| `infrastructure/postgres/` | Pinned non-root PostgreSQL image without the unused `gosu` helper |
| `.github/workflows/` | Phase 0 CI gates |
| `docs/` | Architecture, ADR, phase record, operations guide, test evidence |

`MASTER_PLAN.md` was preserved unchanged and included in the initial commit. No existing application code needed replacement. Ignored local dependencies, browser artifacts, and scanner reports are not source files.

## Decisions, security, and limitations

See [ADR 0001](../decisions/0001-foundation.md) for alternatives, compatibility evidence, and test fixture decisions. Runtime containers use non-root identities. Database ports remain private by default; exposed development ports bind to loopback. Environment files and dependency/browser caches are excluded from source and image contexts.

Authentication, user isolation, RBAC, SSRF prevention, scanning, jobs, matching, AI, notifications, and application automation are absent by design. Health endpoints are public local diagnostics. No claim of production readiness is made.

## Verification and completion boundary

Phase 0 is complete for implementation commit `5d2b9084eaa6cda794dc5407139bab43598dc3e0`. Local functional, static, and security gates passed, and [hosted GitHub Actions run 38544334866](https://github.com/azeez148/career-intelligence-platform/actions/runs/38544334866) completed successfully. All four jobs passed: backend, frontend, containers-and-browser, and secrets. The authoritative results are in [Phase 0 verification](../testing/phase-0.md).

Stop here after verification. Phase 1 needs separate explicit approval and will depend on this application lifecycle, migrations, session handling, and frontend routing foundation.
