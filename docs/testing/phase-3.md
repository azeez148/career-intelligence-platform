# Phase 3 verification evidence

Verified locally on Windows 11 with Docker Desktop 29.8.2 (Linux containers), Python 3.13, and Node 22.22.3 on 2026-10-14, against the final Phase 3 working tree.

- Backend: 156 passed (unit and PostgreSQL/Redis integration); Ruff lint/format and strict mypy passed. The only warning is the pre-existing Starlette `TestClient` deprecation notice.
- Angular: ESLint passed; 10 test files / 30 tests passed; production build passed.
- Playwright: 10/10 Chromium journeys passed against a freshly built isolated Compose stack.
- Runtime: PostgreSQL, Redis, API, and web health checks passed; worker and dispatcher stayed running; Celery registered `discovery.run`; authenticated Redis returned `PONG`, reported `maxmemory-policy noeviction`, and exposed no host port. Readiness returned `database: ok, schema: ok`.
- Alembic reported `0004_career_discovery (head)` and no new upgrade operations.
- Live discovery: a scan of `https://example.com/` ended `unsupported / no_career_source` after one attempt. A scan of the unresolvable `https://phasethreecandidate.com/` retried with backoff and ended `failed / retry_exhausted` after four attempts.
- Broker outage: with Redis stopped, a new scan was accepted (`202 queued`) and stayed `queued` with zero attempts for 20 seconds. After Redis restarted, it reached `unsupported` with exactly one attempt within about 7 seconds. Restarting the worker afterwards logged no traceback.
- `pip-audit` reported no known vulnerabilities; `npm audit --audit-level=high` reported zero vulnerabilities; Gitleaks found no leaks across 16 commits or in the uncommitted files.
- Trivy 0.69.3 found zero HIGH/CRITICAL vulnerabilities in the API, web, PostgreSQL, and pinned Redis runtime images.

## Defect found and fixed during verification

The containerized Celery worker received every `discovery.run` task but never executed one, so scans stayed `queued` and were republished every 30 seconds. Worker processes do not import the HTTP application, so the identity models were never registered and flushing a claimed scan raised `NoReferencedTableError` for `discovery_scans.user_id`. In-process tests did not catch this because the test application imports every model. `app/workers/__init__.py` now registers all mapped tables, and `test_worker_process_registers_every_mapped_table` loads the worker modules in a fresh interpreter (verified to fail without the fix). The browser journey for a completed scan uses a mocked API response, so it does not exercise the real worker; the live discovery and outage checks above do.

## Known limitations observed

- Nginx resolves `api` once at startup. Recreating only the `api` container (for example with `docker compose up --build` after an API-only change) leaves `web` returning 502 until `web` is restarted. This predates Phase 3.
- A task that fails before claiming a scan is not counted as an attempt and is republished on the 30-second stale-dispatch interval until the cause is fixed.

Hosted GitHub Actions is the remaining external verification after push. No Phase 4 behavior is included.
