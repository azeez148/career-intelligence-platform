# Career Intelligence Platform

Angular → FastAPI → PostgreSQL, with Phase 1 accounts, profiles, revocable browser sessions, and database permissions. No job-search functionality is included yet. [MASTER_PLAN.md](MASTER_PLAN.md) governs engineering scope and phase approvals.

## Start locally with Docker

Requirements: Docker Engine/Desktop with Linux containers and Docker Compose 2.24.4 or newer.

1. Copy `.env.example` to `.env`, replace the example database password, and generate three independent random auth secrets as described in [authentication configuration](docs/operations/authentication.md). Keep `DATABASE_URL` consistent for host development and use explicit development mode for local HTTP.
2. Run `docker compose up --build -d --wait --wait-timeout 180`.
3. Open <http://127.0.0.1:8080>. The page should report that the application is connected and ready.

The migration service must succeed before the API starts. PostgreSQL is internal by default; data persists in the project's named volume. `docker compose down` stops services without deleting that volume.

API: <http://127.0.0.1:8000/docs>, `/api/v1/health/live`, and `/api/v1/health/ready`.

## Development and verification

- Python 3.13.16 in containers/CI (also tested locally on 3.13.15); uv 0.12.24; Node 22.22.3; Angular 22.2.2.
- Backend: from `apps/api`, `uv sync --locked`, then `uv run --no-sync pytest -q`. Docker is required for the integration tests. `pytest -m "not integration"` is the explicit unit-only alternative.
- Frontend: from `apps/web`, `npm ci`, `npm run lint`, `npm test`, and `npm run build`.
- Browser: start the isolated test stack described in [testing](docs/testing/phase-1.md), then run `npx playwright install chromium` and `npm run e2e` from `apps/web`.
- Never refresh lockfiles or upgrade dependencies implicitly.

See [local operations](docs/operations/local-development.md), [architecture](docs/architecture/overview.md), [design decisions](docs/decisions/0001-foundation.md), [Phase 0 scope and status](docs/phases/phase-0.md), and [verification evidence](docs/testing/phase-0.md).

See [Phase 1 scope/status](docs/phases/phase-1.md), [authentication design](docs/decisions/0002-authentication-sessions-rbac.md), and [verification evidence](docs/testing/phase-1.md). Phase 2 requires separate explicit approval. This is not a production release.

For commands, browser actions, and expected results after each step, follow the [Phase 1 local checklist](docs/testing/phase-1-local-check.md).
