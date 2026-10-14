# Phase 3 local checklist

Use a disposable project name so cleanup cannot affect normal development data.

1. Copy `.env.example` to `.env`. Set unique `POSTGRES_PASSWORD` and `REDIS_PASSWORD`, three independent auth secrets, `ENVIRONMENT=development`, and `ALLOWED_ORIGINS=["http://127.0.0.1:18080"]` for the test override.
2. Run `docker compose -p career-phase3-check -f compose.yaml -f compose.test.yaml up --build -d --wait --wait-timeout 180`.
3. Run `docker compose -p career-phase3-check -f compose.yaml -f compose.test.yaml ps`. Expect database, Redis, API, and web to be healthy; worker and dispatcher must remain running.
4. Run `docker compose -p career-phase3-check -f compose.yaml -f compose.test.yaml logs --tail 50 worker dispatcher`. Expect `discovery.run` in the worker task list and no traceback.
5. Register and sign in at <http://127.0.0.1:18080>. Add a company with only the name `Phase Three Candidate`, then select **Discover careers**. Expect `needs_input` and `https://phasethreecandidate.com/`; no request is made until selection.
6. Enter `http://127.0.0.1/private`. Expect a validation error and the input to remain. Select the suggested public URL only if you intend to run that request. Expect a child scan whose status survives reload.
7. Open **Discovery** in navigation. Filter by status or company UUID, open a scan, and use **Refresh status**. Polling occurs only for queued/running scans.
8. From `apps/api`, run `uv run --no-sync ruff check .`, `uv run --no-sync ruff format --check .`, `uv run --no-sync mypy`, and `uv run --no-sync pytest -q`.
9. From `apps/web`, run `npm run lint`, `npm test`, `npm run build`, and `npm run e2e`.
10. Run `docker compose -p career-phase3-check -f compose.yaml -f compose.test.yaml down --volumes`. Confirm only the disposable project and volumes are removed.

The deterministic pipeline and SSRF tests use in-process fixtures and do not require a live public company or ATS.
