# Phase 4 verification evidence

Verified locally on Windows 11 with Docker Desktop 29.8.2 (Linux containers), Python 3.13, uv 0.12.24, and Node 22.22.3 between 2026-10-14 and 2026-10-15, against commit `f06e8c4` plus the Step F CI and documentation changes.

| Gate | Result |
|---|---|
| Backend tests (unit, PostgreSQL/Redis integration, Python Playwright browser) | **201 passed** in 4 min 16 s. The only warning is the pre-existing Starlette `TestClient` deprecation notice. |
| Ruff lint and format, strict mypy (86 source files) | Passed |
| Angular ESLint, unit tests, production build | Passed; 11 files / **42 tests** |
| Playwright Chromium journeys against a freshly built isolated stack | **13 / 13 passed** (10 existing + 3 Phase 4) |
| Alembic | `0005_job_extraction (head)`, no new upgrade operations; upgrade from 0004, repeat upgrade, downgrade preserving Phase 0–3 data, and re-upgrade tested |
| Runtime | db, redis, api, web, and fixture-site healthy; worker, browser-worker, and dispatcher running with no tracebacks or errors; browser worker registered `extraction.browser` |
| `pip-audit` (including `playwright` 1.63.0 and `pyee` 13.0.1) | No known vulnerabilities |
| `npm audit --audit-level=high` | 0 vulnerabilities |
| Trivy 0.69.3, strict HIGH/CRITICAL | API, web, PostgreSQL, Redis: 0 |
| Trivy 0.69.3, browser image, fixable-only (approved) | 0 fixable. 61 unfixed (60 HIGH, 1 CRITICAL); 48 inherited from the official base image |
| Gitleaks 8.30.0 | No leaks in git history or in uncommitted files |

## What the tests prove

- **Offline strategy tests** (Greenhouse and Lever fixtures; four HTML fixture sites with reviewed, pinned snapshots):
  - normalization never invents values;
  - Lever pagination and the page limit (reported as `partial`);
  - 404 → `source_not_found`, malformed JSON → `malformed_content`, 5xx/429 → transient;
  - robots rules are respected on API hosts;
  - embedded boards use the public API;
  - navigation decoys and off-host links are ignored, and pagination loops stop;
  - detail pages prefer JSON-LD;
  - tracking parameters are stripped before fetching;
  - a JavaScript shell escalates to the browser stage.
- **Worker integration:**
  - discovery queues one run per source, exactly once;
  - created / updated / unchanged counts are correct;
  - a partial run never closes jobs; a complete run closes missing jobs, and they reopen when seen again;
  - transient retries, then `retry_exhausted`; permanent failures fail immediately;
  - escalation behaves correctly with the browser enabled and disabled;
  - the dispatcher uses the correct task names and recovers expired leases;
  - lower-confidence cross-source copies are hidden;
  - the manual API is owner-scoped, idempotent while a run is active, CSRF-protected, and rate-limited (429).
- **Browser:**
  - a real listener on 127.0.0.1 received zero connections from fetch, `localhost`, iframe, image, and WebSocket attempts;
  - cross-site, POST, and beacon requests never reached the fetch policy;
  - request budget and total timeout are enforced;
  - dialogs and popups don't stall rendering;
  - redirects are followed through the policy.

  A smoke render inside the restricted container (read-only, tmpfs, `no-new-privileges`, uid 10001) blocked the cloud-metadata address 169.254.169.254 and a private WebSocket.
- **End-to-end journeys** (real discovery and extraction against the fixture-site container through `OUTBOUND_TEST_HOSTS`):
  - a static site from discovery to job detail with structured fields; another user gets 404 and an empty explorer;
  - a script-rendered site extracted by the browser worker, labelled `low` confidence with heuristic provenance;
  - explorer filters at a 360 px width with no horizontal overflow.

## Defects found and fixed during implementation

- JSON-LD postings without their own URL collided on the shared page URL, which would have dropped jobs.
- The labelled-section splitter attributed heading text to the previous section.
- Listing groups were chosen per page, which dropped postings on later pages.
- Tracking parameters on listing links broke detail fetches.
- Deeply nested JSON-LD raised an uncaught `RecursionError`.
- Chromium cannot follow fulfilled 3xx navigations; the start document's redirect chain is now resolved first.

## Environment notes

- One earlier full backend run took about 4 hours and failed only the Phase 4 migration test because the machine slept mid-run. That test passes alone in 31 s, and the clean full runs listed above pass.
- Hosted GitHub Actions has **not** run for Phase 3 or Phase 4, because nothing has been pushed.
