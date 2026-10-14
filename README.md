# Career Intelligence Platform

Angular → FastAPI → PostgreSQL with Redis/Celery discovery workers. The approved Phase 3 system provides accounts, private companies and preferences, durable career-source discovery, explicit domain confirmation, and SSRF-safe public HTTP inspection. It does not extract job listings or perform matching. [MASTER_PLAN.md](MASTER_PLAN.md) governs engineering scope and phase approvals.

## Start locally with Docker

Requirements: Docker Engine/Desktop with Linux containers and Docker Compose 2.24.4 or newer.

1. Copy `.env.example` to `.env`, replace both example database and Redis passwords, and generate three independent random auth secrets as described in [authentication configuration](docs/operations/authentication.md). Keep host URLs consistent and use explicit development mode for local HTTP.
2. Run `docker compose up --build -d --wait --wait-timeout 180`.
3. Open <http://127.0.0.1:8080>. The page should report that the application is connected and ready.

The migration service must succeed before the API, worker, and dispatcher start. PostgreSQL and Redis expose no host ports by default; data persists in named volumes. `docker compose down` stops services without deleting those volumes.

API: <http://127.0.0.1:8000/docs>, `/api/v1/health/live`, and `/api/v1/health/ready`.

## Development and verification

- Python 3.13.16; uv 0.12.24; Node 22.22.3; Angular 22.2.2.
- Backend: from `apps/api`, run `uv sync --locked`, then `uv run --no-sync pytest -q`. Docker is required for integration tests. `pytest -m "not integration"` is the unit-only alternative.
- Frontend: from `apps/web`, run `npm ci`, `npm run lint`, `npm test`, and `npm run build`.
- Browser: start the isolated test stack from the [Phase 3 local checklist](docs/testing/phase-3-local-check.md), then run `npx playwright install chromium` and `npm run e2e` from `apps/web`.
- Never refresh lockfiles or upgrade dependencies implicitly.

See [architecture](docs/architecture/overview.md), [Phase 3 status](docs/phases/phase-3.md), [discovery design](docs/decisions/0004-career-discovery.md), [operations](docs/operations/career-discovery.md), and [verification evidence](docs/testing/phase-3.md). This is not a production release.

For commands, browser actions, expected results, and cleanup, follow the [Phase 3 local checklist](docs/testing/phase-3-local-check.md).
