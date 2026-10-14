# Career Intelligence Platform

Angular → FastAPI → PostgreSQL, with Redis/Celery workers and an isolated Chromium worker. The approved Phase 4 system provides:

- accounts, private companies, and preference profiles;
- durable career-source discovery with explicit domain confirmation;
- job extraction from public ATS APIs, structured data, static pages, and script-rendered pages, all through SSRF-safe outbound networking;
- a job explorer with normalized fields, confidence, and provenance.

It does not perform matching. [MASTER_PLAN.md](MASTER_PLAN.md) governs engineering scope and phase approvals.

## Start locally with Docker

Requirements: Docker Engine/Desktop with Linux containers and Docker Compose 2.24.4 or newer.

1. Copy `.env.example` to `.env`. Replace both example database and Redis passwords, and generate three independent random auth secrets as described in [authentication configuration](docs/operations/authentication.md). Keep host URLs consistent and use explicit development mode for local HTTP.
2. Run `docker compose up --build -d --wait --wait-timeout 300`. The first build of the browser-worker image takes a few minutes.
3. Open <http://127.0.0.1:8080>. The page should report that the application is connected and ready.

The migration service must succeed before the API and workers start. PostgreSQL and Redis expose no host ports by default; data persists in named volumes. `docker compose down` stops services without deleting those volumes.

API: <http://127.0.0.1:8000/docs>, `/api/v1/health/live`, and `/api/v1/health/ready`.

## Development and verification

- Versions: Python 3.13.16, uv 0.12.24, Node 22.22.3, Angular 22.2.2, Python Playwright 1.63.0 (browser group only).
- **Backend:** from `apps/api`:
  1. `uv sync --locked --group browser`
  2. `uv run --no-sync playwright install --only-shell chromium`
  3. `uv run --no-sync pytest -q`

  Docker is required for integration tests. Use `pytest -m "not integration and not browser"` for unit tests only.
- **Frontend:** from `apps/web`, run `npm ci`, `npm run lint`, `npm test`, and `npm run build`.
- **Browser journeys:** start the isolated test stack from the [Phase 4 local checklist](docs/testing/phase-4-local-check.md), then run `npx playwright install chromium` and `npm run e2e` from `apps/web`.
- Never refresh lockfiles or upgrade dependencies implicitly.

See [architecture](docs/architecture/overview.md), [Phase 4 status](docs/phases/phase-4.md), [extraction design](docs/decisions/0005-job-extraction.md), [extraction operations](docs/operations/job-extraction.md), [discovery operations](docs/operations/career-discovery.md), and [verification evidence](docs/testing/phase-4.md). This is not a production release.

For commands, browser actions, expected results, and cleanup, follow the [Phase 4 local checklist](docs/testing/phase-4-local-check.md).
