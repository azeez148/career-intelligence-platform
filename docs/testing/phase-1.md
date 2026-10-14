# Phase 1 verification

Status: local verification and all hosted CI gates passed for implementation commit `20648939c17f8dd39154f9bb7ddc957289c20d54`.

[Hosted run 38548891819](https://github.com/azeez148/career-intelligence-platform/actions/runs/38548891819) completed successfully on 2026-10-14 at 10:22:50 UTC (15:52:50 IST): backend, frontend, containers-and-browser, and secrets all passed. Follow the [step-by-step local checklist](phase-1-local-check.md) to reproduce the visible behavior and automated checks.

## Commands

Backend from `apps/api`: `uv sync --locked`, `uv run --no-sync ruff check .`, `uv run --no-sync ruff format --check .`, `uv run --no-sync mypy`, `uv run --no-sync pytest -q --junitxml=test-results/pytest.xml`, `uv run --no-sync pip-audit --progress-spinner off`.

Frontend from `apps/web`: `npm ci`, `npm run lint`, `npm test`, `npm run build`, `npm audit --audit-level=high`.

Browser stack: supply independent temporary secrets and database credentials in an ignored env file, with `ENVIRONMENT=development` and `ALLOWED_ORIGINS=["http://127.0.0.1:18080"]`. Then:

```sh
docker compose --env-file .artifacts/phase1.env -p career-phase1-test -f compose.yaml -f compose.test.yaml up --build -d --wait --wait-timeout 180
# from apps/web
npm run e2e
# from repository root, after verification
docker compose --env-file .artifacts/phase1.env -p career-phase1-test -f compose.yaml -f compose.test.yaml down --volumes
```

The named test project uses disposable tmpfs PostgreSQL storage and ports 18000/18080. Never substitute the development project in its cleanup command. CI generates and masks fresh secrets itself. Existing image tags retain their foundation names; scan the newly built images, not an older cached revision.

## Coverage

Real PostgreSQL tests exercise duplicate registration races, Argon2 storage/rehashing, inactive users, absolute expiry, access validation, rotation/replay, refresh/logout races, immediate revocation, session pagination, ownership, database permission changes, atomic rate counters/reset/refund/cleanup, migration upgrade/downgrade/re-upgrade, and database outage recovery.

Unit tests cover JWT signature/algorithm/required claims, CSRF signature/binding/expiry/origin, production cookie attributes, trusted proxy behavior, invalid configuration, bounded password workers, and existing foundation contracts. Angular tests cover shared refresh, retry boundaries, errors, memory-only user state, return URLs, and form validation. Browser tests exercise real registration/login/profile/refresh/logout workflows through Nginx and PostgreSQL, plus foundation smoke/outage recovery.

## Results

Local verification on 2026-10-14:

| Gate | Result |
|---|---|
| Backend pytest, including disposable PostgreSQL | **31 passed**, no skipped tests |
| Ruff lint and formatting | Passed; 36 Python files formatted |
| mypy strict | Passed; 31 source files |
| Angular tests | **15 passed** across four files |
| ESLint | Passed |
| Production Angular/Docker builds and readiness | Passed |
| Playwright | **5 passed**, including mutation-after-refresh and cross-tab refresh |
| Alembic metadata check | Passed: no new upgrade operations |
| pip-audit | No known vulnerabilities |
| npm audit | 0 vulnerabilities |
| Trivy 0.69.3 API/web/database images | 0 HIGH/CRITICAL findings across all three; no suppressions |
| Gitleaks committed history | Passed; final pushed history also checked in CI |
| Hosted CI | **Passed**, all four jobs; run linked above |

Argon2 local sanity benchmark (five hashes, configured 64 MiB/t=3/p=1, concurrent development workloads): 385.3, 424.9, 370.8, 364.6, 398.4 ms; median 385.3 ms. This is a workstation sanity check, not a production load/SLA claim. Two workers cap hashing work at roughly 128 MiB per API process; capacity saturation is tested.

Resolved during verification: asynchronous Angular test setup, duplicate validation alerts after password clearing, strict route-snapshot typing in tests, ensuring retried mutations use the rotated CSRF cookie value, and revoking a valid access session on logout even when its refresh cookie is missing. The CSRF case has both a unit test and a real-browser profile-write regression; the logout case has a PostgreSQL regression.

Known test warning: Starlette deprecates its HTTPX-based TestClient in favor of HTTPX2; pinned compatibility remains working. Trivy warns that its Alpine 3.24 EOL catalog is incomplete while vulnerability scanning completes successfully. No tests are silently skipped when Docker is unavailable.
