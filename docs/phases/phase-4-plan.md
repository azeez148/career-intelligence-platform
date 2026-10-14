# Phase 4 implementation plan: job extraction and normalization

Status: approved (four recommended decisions in section 4, plus a fixable-only image-scan gate for the browser image approved during implementation), implemented, and locally verified. Hosted CI for Phases 3 and 4 is pending push. See [Phase 4 status](phase-4.md) for deviations.

## 1. Starting evidence and gap assessment

Phase 3 is committed at `e32c4b1` and verified locally (156 backend tests, 30 Angular tests, 10 Playwright journeys, migration, container, outage-recovery, audit, and image gates). Hosted GitHub Actions for Phase 3 has **not** run because the commits have not been pushed; Phase 4 implementation should not begin until that gate is green or explicitly waived.

The repository provides:

- owner-scoped `career_sources` (`generic_page` or `ats`, platform `greenhouse` / `lever` / `workday`, discovery method, evidence codes), unique per company URL and refreshed by later scans;
- `SafeHttpClient`: address-pinned, redirect-revalidating, proxy-free GET client with per-response, per-scan, and redirect budgets; `FetchError` safe codes with transient classification;
- robots evaluation embedded in `DiscoveryPipeline.allowed`;
- a PostgreSQL scan outbox, dispatcher, Celery worker with database leases, bounded retries, and Redis exact-host rate limiting;
- a bounded standard-library HTML parser (`discovery/html.py`) and hardened sitemap XML parsing;
- Angular scan list/detail screens with bounded polling.

Gaps for Phase 4:

- No job, extraction-run, or scan-to-job model exists.
- `SafeHttpClient` sends a fixed HTML/XML `Accept` header, has only scan-sized budgets, and supports GET only.
- Robots policy is private to the discovery pipeline.
- No Python Playwright, and the API image is Alpine, which Playwright's Chromium builds do not support.
- The SSRF policy blocks every non-global address, so the Compose stack cannot run a real end-to-end extraction against a local fixture site. Phase 3 browser tests therefore mock API responses, which is how today's worker defect escaped them.

## 2. Observable outcome and scope boundary

After a discovery scan succeeds, each discovered career source is extracted automatically. A signed-in user can:

- see per-source extraction status, strategy, confidence, job count, and safe failure codes on the scan detail page;
- browse a job explorer for their companies with filters, and open a job detail page;
- re-run extraction for one source (rate-limited).

Extracted jobs are normalized into one model, deduplicated, associated with the run that observed them, and marked closed when a complete later run of the same source no longer lists them.

Explicit non-goals: matching or scoring, AI, preference evaluation, schedules, notifications, saved jobs, resume handling, application automation, login/CAPTCHA bypass, authenticated sources, undocumented private APIs, and claims of universal website support.

## 3. Proposed architecture and execution flow

```mermaid
flowchart LR
    Scan[Discovery worker] -->|success: runs + outbox| DB[(PostgreSQL)]
    API[FastAPI] -->|manual re-run: run + outbox| DB
    Dispatcher --> DB
    Dispatcher --> Redis[(Redis)]
    Redis -->|queue: extraction| Static[Static extraction worker, existing image]
    Redis -->|queue: extraction-browser| Browser[Browser extraction worker, Debian + Chromium]
    Static --> SafeHTTP[SafeHttpClient]
    Browser -->|every browser request intercepted| SafeHTTP
    SafeHTTP --> Web[Public HTTP(S)]
    Static --> DB
    Browser --> DB
```

Strategies run in the order the master plan requires and stop at the first one that yields a confident result:

1. **Official public ATS API**: Greenhouse Job Board API and Lever Postings API.
2. **Structured data**: schema.org `JobPosting` JSON-LD on the source page and on bounded detail pages.
3. **Generic static HTML**: repeated job-like links on the source page, plus bounded detail pages.
4. **Browser rendering**: only when strategies 1–3 find nothing and the page shows JavaScript-rendering signals, or the platform has no permitted static interface. The run is handed to the browser queue as a second stage.

Each strategy is a pure parser over fetched documents, plus a thin fetch plan. All network access goes through `SafeHttpClient`, so parsers are tested offline with fixtures.

## 4. Key decisions requiring approval

1. **Separate extraction runs (recommended)** instead of extending the scan lifecycle. Each source gets an `extraction_runs` row with its own outbox, lease, retries, and terminal state. Discovery history stays unchanged, and one failing source does not fail the scan.
2. **Separate browser worker image (recommended).** Add a Debian-slim image with Python Playwright and its pinned Chromium, used only by an `extraction-browser` worker with concurrency 1. The API, static worker, and dispatcher stay on the small Alpine image. Risk: the Debian/Chromium image may carry HIGH/CRITICAL findings that the current Trivy gate fails on. The plan is to fix these by pinning a current base, never by silently weakening the gate; any unavoidable exception would be documented and brought back for approval.
3. **Workday via public pages only (recommended).** Workday has no documented public job API; the JSON endpoint its frontend calls is undocumented. Phase 4 would use structured data, static HTML, and browser rendering for Workday sources, and would not call that endpoint. Alternative: add a Workday adapter for the frontend endpoint after an explicit terms review.
4. **Test-only fixture allowlist (recommended).** Add a `DISCOVERY_TEST_HOST_ALLOWLIST` setting that maps exact fixture hostnames to fixture containers so the isolated Compose stack can run real discovery-to-jobs journeys. Settings validation rejects it in `production`, it is unset in `compose.yaml`, only `compose.test.yaml` sets it, and the worker logs a startup warning when it is active. Alternative: keep all Playwright journeys API-mocked and rely on backend integration tests, which leaves the live pipeline unproven by browser tests.

## 5. Database and migration design

Migration `0005_job_extraction`:

### `extraction_runs`

- UUID primary key; `user_id`, `company_id`, `source_id`, and optional `scan_id` foreign keys with cascade deletion;
- `trigger` (`discovery` or `manual`); `stage` (`static` or `browser`);
- status constrained to `queued`, `running`, `succeeded`, `partial`, `unsupported`, or `failed`;
- `strategy` (`ats_api`, `structured_data`, `static_html`, `browser`), `confidence` (`high`, `medium`, `low`);
- counts (found, created, updated, unchanged, closed); `complete` flag (false when a budget or page limit truncated the listing);
- attempt count, next attempt, lease expiry, safe failure code, and timestamps;
- a partial unique index allowing at most one `queued` or `running` run per source.

### `extraction_outbox`

The same shape and semantics as `scan_outbox`. The dispatcher is generalized over a small list of (outbox model, task name, queue) entries rather than duplicated.

### `jobs`

- UUID primary key; `user_id`, `company_id`, and `source_id` foreign keys;
- `dedupe_key`: `<platform>:<source job id>` when the source provides an identifier, otherwise the canonical job URL; unique per `(company_id, dedupe_key)`;
- `canonical_url`, `source_job_id`, `title`;
- `location_text` (raw), `work_mode` (`remote`, `hybrid`, `onsite`, `unknown`), `employment_type` (`full_time`, `part_time`, `contract`, `temporary`, `internship`, `unknown`);
- `department`, `description_text` (sanitized plain text, bounded), and `requirements_text`, populated only from an explicitly labelled section;
- `posted_at`, `valid_through`, `first_seen_at`, `last_seen_at`, `closed_at`;
- `extraction_method`, `confidence`, `field_sources` (JSONB map of field → `source` / `structured` / `heuristic`), and `content_hash` for change detection;
- `fingerprint` (normalized title + location + company) and an optional `duplicate_of_job_id` for cross-source duplicates;
- indexes for owner/company/last-seen, open jobs, and fingerprint.

Missing values stay `NULL` or `unknown`; nothing is inferred from unrelated text. No raw HTML, scripts, cookies, or response headers are stored.

### `extraction_run_jobs`

The scan-to-job association: `(run_id, job_id)` primary key with `change` (`created`, `updated`, `unchanged`), so a user can see what each run observed.

### Permissions

Seed `jobs:read:self` and `extractions:create:self` for the member role, with deterministic UUIDs as in earlier migrations. Downgrade removes Phase 4 tables and permission assignments and preserves Phase 0–3 data. Migration tests cover upgrade from `0004`, repeat upgrade, downgrade/re-upgrade, and preservation.

## 6. Extraction rules

### Official APIs

- **Greenhouse**: derive the board token from the recognized source URL, then call `GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true`. Map `id`, `title`, `absolute_url`, `location.name`, `departments`, `updated_at`, and HTML-escaped `content`, which is converted to sanitized text. One request; no pagination.
- **Lever**: derive the site from the source URL, then call `GET https://api.lever.co/v0/postings/{site}?mode=json&skip=N&limit=100`. Map `id`, `text`, `hostedUrl`, `categories.location/commitment/team`, `workplaceType`, `createdAt`, `descriptionPlain`, and labelled `lists`. Paginate with skip/limit within the page budget.
- An API that returns a valid empty list is `succeeded` with zero jobs, not `unsupported`. A 404 for the token or site is `unsupported` with `source_not_found`, which surfaces incorrect source results.

### Structured data

Parse `application/ld+json` blocks (including `@graph` and arrays) for `JobPosting`. Map `title`, `url`, `identifier`, `datePosted`, `validThrough`, `employmentType`, `jobLocation`/`jobLocationType` (`TELECOMMUTE` → remote), `hiringOrganization`, and `description`. Listing pages that only link to detail pages are followed for at most `max_detail_pages`. Malformed JSON blocks are skipped individually.

### Generic static HTML

Group same-origin links by URL path pattern. Treat a group as a job listing only when it has at least three members, job-like path or anchor signals, and no navigation-only context. Follow `rel=next` or numbered page links up to the page limit. Fetch bounded detail pages for the title (`h1`, falling back to the title tag) and main text. Confidence is `low`, and `field_sources` marks heuristic fields.

### Browser rendering

The browser runs only for runs escalated to the `browser` stage. Its safety model:

- Every request from the Chromium context is intercepted with Playwright routing and fulfilled through `SafeHttpClient` (pinned DNS, redirect validation, robots, budgets). The browser itself never opens a network connection.
- Chromium is also launched with an unreachable proxy as defence in depth, so any request that escapes interception fails closed.
- WebSockets, service workers, downloads, permissions, popups, and file chooser access are blocked. Each run gets a fresh non-persistent context. A fixed viewport and user agent are used, plus a hard navigation and total time limit.
- Only script, document, XHR/fetch, and stylesheet resources are allowed; images, media, and fonts are aborted. Separate per-render request and byte budgets apply.
- After rendering, the same structured-data and static-HTML parsers run on the rendered DOM. Browser rendering never performs clicks, logins, form submission, or CAPTCHA handling.

### Normalization, deduplication, and closing

- Text is unescaped and stripped of markup through the bounded parser, whitespace is collapsed while keeping paragraph and bullet breaks, and length is capped.
- Canonical URLs are normalized with the existing URL rules, with fragments and known tracking parameters removed generically.
- Within a source, upsert by `dedupe_key`; a content-hash change marks the job `updated`.
- Across sources of the same company, a lower-confidence job with an equal fingerprint gets `duplicate_of_job_id` set to the higher-confidence job and is hidden by default in the job explorer.
- After a `complete` successful run, open jobs of that source not seen in the run receive `closed_at`. Partial or failed runs never close jobs.

### Budgets (configurable, tested defaults)

| Limit | Default |
|---|---|
| Responses per static run | 60 |
| Bytes per static run | 25 MiB |
| Listing pages per source | 10 |
| Detail pages per run | 40 |
| Jobs per source | 1,000 |
| Description length | 100,000 characters |
| Browser requests per render | 80 |
| Browser bytes per render | 20 MiB |
| Browser total time per render | 45 s |
| Task soft/hard limit (static) | 150 s / 160 s |
| Task soft/hard limit (browser) | 120 s / 130 s |

The existing per-host rate limiter and robots rules apply to every request, including API hosts.

## 7. Shared HTTP and policy changes

- `SafeHttpClient` gains a per-call `accept` argument (JSON for API strategies), injected `FetchLimits` per run type, and an exposed budget state so runs can report `complete=false` instead of failing when a listing budget ends.
- Robots evaluation moves from `DiscoveryPipeline` into `integrations/robots.py` and is reused by discovery, extraction, and the browser route handler. Discovery behaviour is unchanged; existing tests prove it.
- GET remains the only method. No strategy needs POST under the recommended Workday decision.

## 8. API contract

All routes are owner-scoped and authenticated; mutations require CSRF.

- `GET /api/v1/jobs?company_id=&source_id=&q=&work_mode=&employment_type=&status=open|closed|all&include_duplicates=false&offset=0&limit=20` returns `{items, next_offset}`. `q` is a bounded case-insensitive title/department substring search.
- `GET /api/v1/jobs/{job_id}` returns the full normalized job with provenance, confidence, first/last-seen dates, and the runs that observed it.
- `GET /api/v1/scans/{scan_id}` is extended with per-source extraction run summaries.
- `GET /api/v1/extractions/{run_id}` returns run detail and counts.
- `POST /api/v1/sources/{source_id}/extractions` returns `202` with the active run if one exists, otherwise a new manual run. It is rate-limited per user and per source through the existing PostgreSQL limiter.

Status semantics match Phase 3: 401, 403, 404 for foreign or missing resources, 409, 422, and 429. New safe failure codes include `source_not_found`, `api_unavailable`, `no_jobs_recognized`, `render_failed`, `render_timeout`, `page_budget_exceeded`, and `malformed_content`.

## 9. Frontend behavior

- **Scan detail**: a per-source extraction panel with status, strategy, confidence badge, counts, `complete` indicator, safe outcome text, a link to that source's jobs, and a permission-gated **Re-extract** action. Polling stays bounded and stops on terminal states.
- **`/jobs`**: the job explorer, with company/source/work mode/employment type/status filters, text search, bounded pagination, empty and failed states, and a narrow-viewport layout.
- **`/jobs/:id`**: job detail with the description rendered as preserved-whitespace text (never as HTML), unknown fields shown as "Not stated", the source link opened with safe external-link attributes, and a provenance and confidence section.
- Navigation, permission gating, safe return URLs, and resource error mappings are extended. No match scores or AI features are added.

## 10. Planned files

Backend, created:

- `app/modules/extraction/{__init__,models,schemas,service,router,runner}.py`
- `app/modules/extraction/strategies/{__init__,greenhouse,lever,structured_data,static_html,browser}.py`
- `app/modules/jobs/{__init__,models,schemas,service,router,normalize}.py`
- `app/integrations/{robots,browser}.py`
- `migrations/versions/0005_job_extraction.py`
- fixture directories under `tests/fixtures/extraction/` and focused test modules

Backend, modified:

- `integrations/http.py`, `modules/discovery/pipeline.py` (robots extraction only), `workers/{tasks,dispatcher,celery_app}.py`
- `core/config.py`, `db/models.py`, `api/router.py`
- `pyproject.toml`/`uv.lock` (Python Playwright, pinned after compatibility review)

Infrastructure:

- new `apps/api/Dockerfile.browser`
- `compose.yaml` (static worker queue list and a new `browser-worker` role), `compose.test.yaml` (fixture site container and allowlist)
- `.github/workflows/ci.yml` (browser image build and scan, Python Playwright tests)

Frontend:

- `src/app/jobs/{job-model,job.service,job-list,job-detail}.ts` with specs
- scan detail extraction panel; `app.routes.ts` and navigation
- `e2e/jobs.spec.ts`

Documentation:

- ADR `0005-job-extraction.md`, `docs/operations/job-extraction.md`, Phase 4 status/verification/local-check documents, README, and architecture updates.

## 11. Test strategy

Strategy and normalizer unit tests run offline from versioned fixtures, with no live company or ATS:

- **API extraction**: Greenhouse and Lever fixtures, empty boards, Lever pagination across pages, 404 tokens (incorrect source), 429/5xx retry classification, malformed JSON, and missing fields remaining `NULL`/`unknown`.
- **Structured data**: single, array, and `@graph` JSON-LD; malformed blocks; listing-to-detail follow; remote/hybrid mapping.
- **Static HTML**: listing detection thresholds, navigation false positives, `rel=next` and numbered pagination with loop protection, and detail extraction.
- **Normalization**: text sanitization (scripts, entities, nested markup), URL canonicalization, dedupe keys, fingerprints, and content-hash change detection.
- **Browser extraction (Python Playwright)**: fixture pages served only through route interception; JS-rendered listings; proof that a script requesting a private address, a different host, or a WebSocket is blocked; budget and timeout termination; no popups or downloads.
- **Integration (PostgreSQL/Redis)**: discovery success enqueues one run per source; duplicate delivery and expired leases; retries and exhaustion; static-to-browser escalation; closing only after complete runs; cross-source duplicates; owner isolation; permissions; CSRF; rate limits; migration upgrade/downgrade/preservation.
- **Regression**: a source fixture suite that pins expected normalized output per fixture, so parser changes show diffs.
- **Worker process**: the fresh-interpreter model registration check added in Phase 3 is extended to the browser worker image.
- **Angular unit**: services, explorer filters and pagination, detail rendering as text, unknown values, extraction panel polling and re-extract.
- **Playwright journeys** (under decision 4): a real Compose run where a fixture company with Greenhouse-shaped, JSON-LD, static, and JS-rendered fixture sources goes discovery → extraction → job explorer → detail, plus two-user isolation, re-extract, an inaccessible source, a narrow viewport, and all existing journeys.

Full gates are the same as Phase 3, plus the browser image build/health and its Trivy scan. Unavailable checks are reported as NOT VERIFIED.

## 12. Incremental implementation order and local checks

- **A. Migration, models, permissions, jobs read API.** Local check: `alembic upgrade head` and `alembic check` report no drift; jobs list is empty and owner-scoped; a foreign job returns 404.
- **B. HTTP/robots refactor, API strategies, normalizer, run worker, outbox.** Local check: discovery tests unchanged and passing; a fixture Greenhouse/Lever source produces normalized jobs; repeat runs report `unchanged`; a removed job closes only after a complete run.
- **C. Structured-data and static HTML strategies.** Local check: the fixture regression suite passes, malformed content is skipped safely, and pagination stops at limits.
- **D. Browser worker image and strategy.** Local check: the browser image builds, scans clean, and starts; JS fixtures extract; private-address, WebSocket, and cross-origin escape tests pass.
- **E. Angular extraction panel and job explorer.** Local check: jobs are visible and filterable; detail renders text only; polling stops.
- **F. Full verification and documentation.** Run every gate from a fresh disposable stack, record exact evidence, and update the ADR, operations, architecture, README, and local checklist.

## 13. Acceptance criteria

Phase 4 is complete only when:

- Greenhouse and Lever sources extract through their public APIs with pagination where applicable;
- structured data, static HTML, and browser strategies extract from the fixture sources, in the required order, with honest confidence;
- every request, including every browser sub-request, passes the Phase 3 SSRF, robots, rate, and budget policy, proven by tests;
- jobs are normalized without fabricated values, deduplicated within and across sources, associated with runs, and closed only after complete runs;
- failures, unsupported sources, incorrect sources, and partial listings are reported with safe codes;
- the job list/detail APIs and Angular explorer work with owner isolation, permissions, and CSRF;
- migration, regression, browser, dependency, container, secret, and hosted CI gates pass;
- design, operations, limitations, and exact test evidence are documented;
- no matching, AI, schedules, notifications, or saved-job features are introduced.

## 14. Material tradeoffs and known limitations

- Heuristic HTML extraction will miss or mis-group some sites. Its results are marked `low` confidence, and sites that yield nothing are reported unsupported rather than guessed.
- The browser worker adds a larger image, a larger attack surface, and slower runs. Interception-only networking limits SSRF risk but not Chromium vulnerabilities, so the image must be kept current.
- Jobs are stored per owner because companies are per owner; two users tracking the same company store separate copies. This is acceptable for the MVP and is revisited if usage requires shared sources.
- Exact-host rate limiting from Phase 3 still treats subdomains independently.
- Job descriptions are untrusted text. Phase 5 must treat them as data, never instructions, when any AI provider sees them.
- The pre-existing Nginx single-resolution behaviour (restart `web` after recreating `api`) remains documented and unchanged.

## 15. Approval boundary

This document is the reviewable Phase 4 plan. Implementation begins only after explicit approval of the plan and of the four decisions in section 4. It proceeds through steps A–F with a local check reported after each step, and stops before Phase 5.
