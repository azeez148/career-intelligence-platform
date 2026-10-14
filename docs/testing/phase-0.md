# Phase 0 verification

Date: 2026-10-14 (Asia/Calcutta). Evidence below distinguishes executed local checks from hosted CI.

## Reproduce backend checks

From `apps/api`:

```sh
uv sync --locked
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync mypy
uv run --no-sync pytest -q
uv run --no-sync pip-audit --progress-spinner off
```

`pytest -m "not integration"` runs the unit-only subset. `pytest -m integration` requires Docker and creates a disposable, digest-pinned PostgreSQL 17.11 container. Missing Docker is a test error, not a silent skip. The migration test verifies an unmigrated database, upgrade, idempotent upgrade, downgrade, re-upgrade, actual server outage, bounded readiness, independent liveness, and recovery after restart. The second integration test proves SQLAlchemy session connectivity and absence of business tables.

The host commands were executed with the virtual environment's executables directly where sandbox cache permissions prevented `uv run`; they use the same locked packages.

## Reproduce frontend checks

From `apps/web`, using Node 22.22.3:

```sh
npm ci
npm run lint
npm test
npm run build
npm audit --audit-level=high
npx playwright install chromium
```

For local Windows verification the project-local Node executable invoked the project-local npm CLI explicitly, avoiding the system's Node 22.22.0 version-manager shim. The Angular build/test processes needed permission to spawn esbuild. Sandbox `EPERM` was not counted as an application test failure or a successful check.

## Isolated browser/container tests

Set `POSTGRES_PASSWORD` in the environment to a disposable URL-safe test value. Use a separate project name; this override replaces the development volume with ephemeral tmpfs and publishes ports 18000/18080.

```sh
docker compose -p career-phase0-test -f compose.yaml -f compose.test.yaml up --build -d --wait --wait-timeout 180
```

From `apps/web`, run `npm run e2e`. It requires the real API/database stack; there is no mocked successful readiness result. One test intercepts a single 503 response to exercise the error UI, then retries against the real API. `PLAYWRIGHT_BASE_URL` overrides the default URL.

After collecting evidence, from the repository root:

```sh
docker compose -p career-phase0-test -f compose.yaml -f compose.test.yaml logs --no-color
docker compose -p career-phase0-test -f compose.yaml -f compose.test.yaml down --volumes
```

Only use that cleanup command with the disposable test project. It must not target development data.

## Results

| Check | Result | Evidence |
|---|---|---|
| Locked backend installation | PASS | Python 3.13.15 host and 3.13.16 Alpine; all locked runtime wheels install |
| Backend unit tests | PASS | 14 tests on host and 14 inside the final Python/Alpine test stage |
| PostgreSQL integration | PASS | 2 tests on final PostgreSQL 17.11; migrations, bounded outage, and recovery |
| Complete backend run | PASS | 16 tests; final database patch separately rerun through both integration tests |
| Ruff lint/format | PASS | All checks passed; 17 files formatted |
| Strict mypy | PASS | No issues in 14 source files |
| Clean frontend install | PASS | `npm ci` after exact direct-dependency pinning |
| ESLint | PASS | `npm run lint`, including Angular templates |
| Angular unit tests | PASS | 4 tests across 2 files |
| Strict Angular production build | PASS | Host and Linux build; initial bundle approximately 219.89 kB |
| Fresh Compose build/start | PASS | Database/API/web healthy; migration service exit 0; final non-root images |
| PostgreSQL named-volume startup | PASS | Separate disposable project; `SELECT 1` on initial startup and after container recreation with the same volume |
| Playwright Chromium | PASS | 2 tests against final stack, 4.7 seconds; actual API/proxy response and outage/retry |
| Python dependency audit | PASS | `pip-audit`: no known vulnerabilities |
| npm dependency audit | PASS | 0 vulnerabilities reported |
| API runtime image | PASS | Trivy 0 HIGH/CRITICAL findings |
| Web runtime image | PASS | Trivy 0 HIGH/CRITICAL findings |
| Database runtime image | PASS | Trivy 0 HIGH/CRITICAL findings |
| Workflow static validation | PASS | actionlint 1.7.7, including database scan job |
| Secret scanning | PASS | Gitleaks 8.30.0; committed history scanned with redaction; no leaks found |
| Hosted GitHub Actions | NOT VERIFIED | No push or hosted workflow execution performed |

The 16-test complete backend run preceded the final PostgreSQL image pin; the 2 integration tests were then rerun successfully against that final pin. The application code was unchanged by this database image selection. Container-unit results separately prove Python 3.13.16/musl compatibility. Tests are not being counted as hosted CI.

Security image IDs and counts are recorded in [security-summary.json](security-summary.json). Full local Trivy JSON reports are in ignored `.artifacts/`; Playwright reports are in ignored `apps/web/playwright-report/`; pytest JUnit output is in ignored `apps/api/test-results/`. No vulnerability suppression or `--ignore-unfixed` was used. The HIGH/CRITICAL gate does not certify the absence of all lower-severity findings.

The disposable named-volume project was removed after testing. The isolated browser stack is also stopped after collecting evidence; downloaded images and dependency/browser caches remain available locally.

## Resolved issues and observations

- Docker Desktop was initially stopped; it was started with permission, enabling real integration checks.
- A test failed recovery because Docker changed the automatically published host port on restart. A diagnostic observed port 54880 becoming 54703. The fixture now binds a stable chosen free port; the complete backend suite subsequently passed.
- A Pydantic field named `schema` shadowed a BaseModel method. The internal attribute is now `schema_status` with the unchanged public JSON alias `schema`.
- Pydantic's mypy plugin makes environment-loaded required settings type-check correctly. Invalid configuration hides input values in printed validation errors.
- Starlette emits a deprecation warning for HTTPX TestClient. It remains functional; no test warning has been hidden.
- Initial API image scanning found Debian OS and bundled installer vulnerabilities despite a clean application dependency audit. Moving to a reviewed Python 3.13 Alpine base and removing unused installation tooling resolved them. The web base was updated to stable Nginx 1.30.5. PostgreSQL's unused `gosu` helper was removed with verified direct non-root startup. All three final runtime scans passed.

## CI boundary

GitHub Actions is configured for push, pull request, and manual dispatch, but local tests are not a hosted CI run. No repository push is part of this implementation. Hosted CI is **NOT VERIFIED** until the commits are published and the configured workflow succeeds.
