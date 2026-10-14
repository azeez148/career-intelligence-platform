# Phase 2 verification evidence

Status: local verification complete; hosted GitHub Actions pending. Pending checks are not claimed as passed.

The [local checklist](phase-2-local-check.md) provides commands and expected results after each implementation step. All Phase 0/1 suites remain active; migration-head/table assertions now include the approved Phase 2 schema. No dependency versions changed.

| Gate | Result |
|---|---|
| Backend unit/integration regression | 129 passed in the final full run |
| Ruff and strict mypy | Passed |
| Angular unit tests | 25 passed across seven files |
| ESLint and production Angular build | Passed |
| Docker build/start/migration/readiness | Passed; revision 0003 is current and Alembic reports no pending operations |
| Playwright Chromium | 8 passed, including all prior journeys |
| pip-audit | No known vulnerabilities |
| npm audit | No known vulnerabilities |
| Runtime image scans | API, web, and database: zero HIGH/CRITICAL findings |
| Secret scan | Eight commits scanned; no leaks found |
| Hosted GitHub Actions | Pending |

Coverage includes strict pure URL validation and IDNA, resource bounds, typed JSON documents, conflicts/weight allocations, concurrent company uniqueness, all eight permission checks, owner isolation, migration data/assignment preservation, safe error output, new-route refresh with rotated CSRF, retained rejected form input, multiple profiles, responsive forms, and cross-tab logout.

Resolved during implementation: Alembic's generated JSONB dialect imports, shared pytest fixture extraction, and route-parameter test doubles returning `undefined` instead of Angular's `null`. No security checks were disabled and no dependency suppressions were added.

Known environment warnings remain: pinned Starlette emits the existing TestClient/HTTPX deprecation warning, and sandboxed local pytest can warn about a cache directory owned by an earlier elevated run. Elevated full runs produce the test artifacts. These warnings are not test failures or skipped integration checks.

Local disposable stack: `career-phase2-test`, test ports 18000/18080, ignored `.artifacts/phase2.env` with generated independent credentials. CI retains its established isolated project name and discovers all new test files automatically. Image tags retain their historical `phase0` names; scans apply to freshly rebuilt images, not the original foundation artifacts.
