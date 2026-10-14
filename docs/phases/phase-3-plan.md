# Phase 3 implementation plan: generic career discovery

Status: approved by the user; implementation in progress.

## 1. Starting evidence and gap assessment

Phase 2 is complete at commit `90fd47e`; the worktree is clean and the final hosted workflow passed all four jobs. The repository currently provides:

- owner-scoped companies with optional name, website URL, and careers URL;
- strict persistence-time URL syntax validation without DNS or HTTP access;
- authenticated sessions, CSRF protection, database-driven permissions, and owner-scoped queries;
- PostgreSQL as the authoritative store, Alembic migrations, and safe JSON errors;
- Angular protected routes with one-time session refresh and real Playwright browser tests;
- Docker Compose for PostgreSQL, API, web, migrations, and isolated tests.

No Redis service, Celery worker, queue/outbox, scan model, discovery module, outbound HTTP policy, DNS validation, career-source model, scan API, or discovery UI exists. The current `core/urls.py` is suitable for validating stored input but deliberately does not make a stored URL safe to fetch. Phase 3 must validate every DNS resolution and redirect at request time.

## 2. Observable outcome and scope boundary

A signed-in user with the required permissions can start discovery for one of their companies, see the persisted scan move through its lifecycle, and inspect either:

- one or more discovered career sources with the evidence and recognized source type;
- low-confidence domain candidates that require explicit user selection;
- an unsupported or failed outcome with a stable, safe reason code.

The discovery worker will inspect only bounded public metadata needed to locate a career source: robots directives, a homepage, a small set of sitemap documents, and candidate career pages. It will recognize reusable ATS platforms but will not extract or store vacancies.

Explicit non-goals are job extraction, job normalization, JavaScript browser extraction, recurring schedules, notifications, matching, AI, resume handling, application automation, CAPTCHA or login bypass, authenticated/private websites, proxy support, and claims of universal website support. Python Playwright remains deferred to Phase 4 because this phase does not render or extract JavaScript job pages.

## 3. Proposed architecture and execution flow

```mermaid
flowchart LR
    UI[Angular scan screens] --> API[FastAPI scan API]
    API -->|scan + outbox transaction| DB[(PostgreSQL)]
    Dispatcher[Outbox dispatcher] --> DB
    Dispatcher --> Redis[(Redis broker/rate limits)]
    Redis --> Worker[Celery discovery worker]
    Worker --> SafeHTTP[SSRF-safe HTTP transport]
    SafeHTTP --> PublicWeb[Public DNS and HTTP(S)]
    Worker --> DB
    UI -->|bounded polling| API
```

The API never performs remote discovery in its request process. PostgreSQL remains authoritative for scan state and results; Redis is a broker and short-lived domain-rate-limit store, not the source of user-visible status. A transactional outbox closes the database-commit/message-publish gap. The dispatcher may publish a message more than once, so the task and state transitions must be idempotent.

The smallest required runtime additions are one Redis container, one worker process, and one outbox-dispatcher process using the existing API image. These are runtime roles of the modular monolith, not independently versioned services.

## 4. Database and migration design

Create migration `0004_career_discovery.py` with four tables:

### `discovery_scans`

- UUID primary key, `user_id` and `company_id` foreign keys with cascade deletion;
- status constrained to `queued`, `running`, `needs_input`, `succeeded`, `unsupported`, or `failed`;
- optional selected/start URL, attempt count, next-attempt time, worker lease expiry, safe failure code, and created/started/completed/updated timestamps;
- optional resolved website URL, resolution confidence, and bounded resolution-evidence codes; these describe the scan result and never silently rewrite the company row;
- optional parent scan ID for a user-selected continuation, allowing the original ambiguous result to remain auditable;
- owner/created and company/created indexes;
- a partial unique index preventing more than one `queued` or `running` scan per company.

### `discovery_candidates`

- UUID primary key and scan foreign key with cascade deletion;
- normalized URL and hostname, confidence (`low`, `medium`, `high`), and a bounded evidence-code array/JSON document;
- unique `(scan_id, url)` constraint;
- no copied remote HTML, snippets, cookies, headers, or DNS addresses.

### `career_sources`

- UUID primary key plus owner, company, and producing-scan foreign keys;
- normalized public URL, source kind (`generic_page` or `ats`), optional recognized platform code, discovery method, and bounded evidence codes;
- owner/company indexes and unique `(company_id, url)` constraint;
- upsert behavior so repeated scans refresh evidence without duplicating a source.

### `scan_outbox`

- scan ID primary/foreign key, availability time, publish-attempt count, last safe error code, and dispatched timestamp;
- dispatcher selection with `FOR UPDATE SKIP LOCKED`;
- deletion/retention only after the associated scan reaches a terminal state.

Seed `scans:read:self`, `scans:create:self`, and `scans:update:self` with deterministic UUIDs and grant them only to the existing seeded member role. Existing custom roles receive no implicit capabilities. Downgrade deletes Phase 3 scan/source/outbox rows and these permission assignments while preserving all Phase 0–2 account, company, and preference data.

## 5. API contract

All routes require an authenticated live session and owner-scoped queries. Mutations require the existing JSON content type and CSRF token.

### Start and list scans

- `POST /api/v1/companies/{company_id}/scans` → `202` with the existing active scan or a newly created scan.
- `GET /api/v1/scans?company_id={uuid}&status={optional}&offset=0&limit=20` → `{items,next_offset}` with limit 1–100 and bounded offset.
- `GET /api/v1/scans/{scan_id}` → scan detail, candidates, and discovered career sources.

Starting a scan verifies company ownership, consumes configurable per-user and per-company request limits through the existing PostgreSQL rate-limit service, and creates the scan and outbox row in one transaction. A repeated request while work is active returns the same scan rather than queueing duplicate work.

### Resolve ambiguity

- `POST /api/v1/scans/{scan_id}/selection` with exactly one of `candidate_id` or `website_url` → `202` with a new child scan.

Only an owned `needs_input` scan can be continued. Candidate IDs are scoped through the owned scan. A manually entered URL uses the same strict syntax normalization as companies and is still revalidated by the outbound security layer. Selection does not silently overwrite the saved company website; the user can make that separate explicit edit.

Status semantics are stable and safe: 401 authentication, 403 permission/CSRF, 404 missing or foreign-owned resources, 409 invalid state transition, 422 invalid input, and 429 scan submission limit. Remote failure details use allowlisted codes such as `dns_blocked`, `robots_disallowed`, `tls_error`, `timeout`, `response_too_large`, `unsupported_content`, `no_career_source`, and `retry_exhausted`; raw target content and resolver errors are not reflected.

## 6. Discovery rules

### Starting target selection

1. An explicit careers URL is the first target.
2. Otherwise an explicit website URL is the homepage target.
3. A name-only company never triggers an automatic network request. A conservative resolver may produce a low-confidence `https://<normalized-name>.com/` candidate only when the entire name converts unambiguously to one valid ASCII DNS label. The UI also permits a user-entered URL. Either path requires explicit selection before any request.

This intentionally limited name-resolution rule avoids silently attaching a similarly named organization. It will miss many legitimate country-code, multiword, and non-Latin domains; those scans return `needs_input` and explain that a website must be selected or entered. No search engine scraping or unapproved external search provider is introduced.

### Bounded discovery pipeline

For a selected public target, the worker will:

1. retrieve and evaluate `robots.txt` for the configured product user agent;
2. fetch the selected page with redirects handled manually;
3. inspect canonical metadata and bounded visible title/organization signals without declaring ownership from a name match alone;
4. parse same-page links and score generic career signals such as careers, jobs, vacancies, and join-us;
5. inspect sitemap URLs declared by robots plus `/sitemap.xml`, with bounded recursion and entries;
6. validate and inspect only the highest-scoring bounded candidate pages;
7. classify a generic career page or a recognized ATS source and persist evidence codes.

The final canonical homepage is recorded as the resolved website only when the starting URL was supplied on the company or explicitly selected by the user and the redirect chain remains safe. Name/text similarity can contribute evidence but cannot promote an unconfirmed candidate. Discovery never mutates `companies.website_url` or `companies.careers_url` automatically.

Initial ATS recognition is limited to reusable public patterns for Greenhouse Job Board, Lever hosted jobs, and Workday career sites. Detection uses platform host/path rules and stable document signatures. These adapters identify a source only; Phase 4 decides whether and how its public job interface is extracted. Unsupported or blocked sites are reported honestly.

Default resource budgets will be configuration-bounded: at most 12 responses per scan, 5 redirects per response chain, 2 MiB decoded body per response, 10 MiB total decoded content, 2,000 sitemap URLs examined, 3 sitemap documents, 10-second read timeout, 5-second connection timeout, and a 75-second hard worker time limit. Exact defaults will be tested and documented; production settings retain safe upper bounds.

## 7. Outbound HTTP and SSRF policy

Create one `SafeHttpClient`/transport boundary and prohibit direct `httpx` calls from discovery strategies.

For every initial URL and every redirect target it will:

- accept HTTP/HTTPS only, standard scheme ports only, no credentials/fragments/backslashes/control characters, and no IP-literal host input;
- normalize IDNA hostnames and reject the existing local/special suffixes;
- resolve DNS immediately before connection and reject the target if any selected address is loopback, private, link-local, multicast, reserved, unspecified, documentation-only, carrier-grade NAT, or otherwise non-global;
- pin the validated address for the socket connection so a second resolver lookup cannot redirect the connection, while preserving the original host for the HTTP `Host` header, TLS SNI, and certificate validation;
- verify the connected peer address and reject mismatches;
- disable environment proxies and automatic redirects, validate every redirect independently, and cap redirect loops;
- use normal CA verification, no client credentials, no cookie persistence between scans, a fixed identifying user agent, strict timeouts, bounded connection pools, streamed decoded-body limits, and an aggregate scan budget.

HTTPX 0.28.1 supports a custom transport boundary. Implementation will encapsulate the compatible low-level connection backend in `integrations/http.py`; if it uses `httpcore` directly, `httpcore==1.0.9` becomes an explicit dependency rather than relying on a transitive package. Unit and integration tests must prove DNS rebinding resistance and actual address pinning, not only a preflight `ipaddress` check.

Untrusted sitemap XML will use a hardened parser (`defusedxml`, currently 0.7.1) with DTD/entities disabled. HTML parsing will use a bounded standard-library parser unless implementation evidence requires a reviewed dependency.

## 8. Queue reliability, retries, and domain rate limiting

Add pinned Celery with Redis support after a Python 3.13 compatibility lock review; current candidate releases are Celery 5.6.3 and redis-py 8.1.0. Redis will require an independent password, stay off host ports, use a dedicated broker database/key prefix, disable eviction, and use AOF persistence in the normal stack. The isolated test stack uses disposable storage.

The dispatcher publishes deterministic task IDs derived from scan IDs and marks outbox rows dispatched only after broker acknowledgement. A periodic recovery pass republishes stale undispatched rows. The worker claims a queued scan with an atomic status/lease update; duplicate deliveries exit harmlessly when the scan is terminal or actively leased.

Tasks use late acknowledgement, prefetch one, bounded concurrency, worker-lost rejection, soft/hard time limits, and retry only transient classes: broker errors, timeouts, temporary DNS failures, connection failures, and HTTP 429/502/503/504. Retries use capped exponential backoff with jitter and persist attempt/next-attempt state. Validation failures, private-address resolutions, robots denial, unsupported content, most 4xx responses, and exhausted budgets are terminal and never retried blindly.

Before each outbound request, an atomic Redis operation reserves a hostname-level interval. If unavailable, the task retries after the returned delay without making the request. Exact hostname is used rather than a guessed registrable domain, avoiding an unreviewed public-suffix dependency; this limitation is documented. The scan-wide request budget prevents subdomain fan-out abuse.

Redis is not used as a Celery result backend. API status always comes from PostgreSQL, so broker restarts cannot rewrite user-visible history.

## 9. Frontend behavior

Extend the company list with a permission-gated **Discover careers** action and last-scan summary. Add lazy routes:

- `/scans` for owner-scoped scan history with company/status filtering and bounded pagination;
- `/scans/:id` for status, timestamps, safe outcome text, candidates, and discovered source URLs displayed as text;
- candidate selection/manual website form shown only for `needs_input` scans.

The detail page polls only while status is `queued` or `running`, uses a fixed bounded interval, stops on terminal state/navigation/logout, and offers a manual refresh. It preserves selection input on rejected saves, handles 401 refresh through the existing interceptor, and never inserts fetched HTML. Source URLs are text by default; if opened, they use explicit safe external-link attributes.

Update protected-route recognition, safe return URLs, logout redirects, navigation permissions, responsive styles, and resource error mappings. No dashboard, job list, progress percentages, or fabricated scan stages are added.

## 10. Planned files

Create backend files:

- `app/modules/discovery/{models,schemas,service,router,pipeline,candidates,html,sitemaps,ats}.py`
- `app/modules/discovery/__init__.py`
- `app/integrations/http.py`
- `app/workers/{celery_app,tasks,dispatcher}.py` and package initializers
- `migrations/versions/0004_career_discovery.py`
- focused tests for network policy, pipeline rules, queue/idempotency, API ownership, migration preservation, and worker/Redis integration.

Modify backend composition/configuration:

- `pyproject.toml` and `uv.lock` for reviewed pinned queue/XML/network dependencies;
- `core/config.py`, `core/errors.py`, `core/form_errors.py`, `db/models.py`, `api/router.py`, `main.py`, and existing test fixtures/migration assertions;
- `Dockerfile` only if the shared runtime command/import layout requires it.

Create frontend files:

- `src/app/scans/scan-model.ts`, `scan.service.ts`, `scan-list.ts`, `scan-detail.ts`, and focused unit specs;
- `e2e/discovery.spec.ts` using deterministic local fixture servers rather than the public internet.

Modify `app.routes.ts`, application navigation/logout handling, auth interceptor/safe-return rules, company list/service, shared errors/styles, and relevant auth tests.

Modify infrastructure and documentation:

- `compose.yaml`, `compose.test.yaml`, `.env.example`, `.github/workflows/ci.yml`;
- `README.md`, `docs/architecture/overview.md`;
- new ADR `docs/decisions/0004-career-discovery.md`;
- new operations guide `docs/operations/career-discovery.md`;
- completion report and verification/local-check documents for Phase 3.

No empty Phase 4 extraction/jobs modules will be created.

## 11. Test strategy

### Pure unit tests

- name-only candidate generation never performs DNS/network access and never auto-selects;
- link scoring, relative/cross-host URL handling, canonical evidence, deduplication, ATS recognition, robots rules, sitemap recursion, malformed HTML/XML, and all resource bounds;
- status transition matrix, retry classification/backoff bounds, safe failure-code mapping, and active-scan idempotency;
- URL normalization plus IPv4/IPv6, alternate numeric forms, Unicode/IDNA, credentials, ports, controls, redirect loops, and encoded-host edge cases.

### Network-security integration tests

Use controlled local DNS/socket fakes and disposable HTTP/TLS servers. Prove that:

- loopback, RFC1918, link-local, metadata-style, reserved, and mixed public/private answers are blocked;
- a host that changes from public to private between validation and connection cannot reach the private listener;
- the transport connects only to its pinned public address while keeping correct Host/SNI validation;
- each redirect is re-resolved/revalidated;
- environment proxy variables are ignored;
- timeouts, streaming size limits, decompression limits, response-count limits, and total budgets stop work predictably;
- remote bodies, DNS details, and credentials do not enter API errors or normal logs.

No test will depend on a live public company, DNS provider, ATS, or search engine.

### PostgreSQL/Redis/worker integration tests

- migration upgrade from `0003`, repeat upgrade, downgrade/re-upgrade, and preservation of Phase 0–2/custom-role data;
- enqueue transaction/outbox recovery across broker outage and dispatcher restart;
- duplicate delivery and expired worker lease produce one terminal scan and no duplicate source;
- transient failures retry with bounded attempts; permanent failures do not;
- Redis hostname rate limiting delays competing scans and does not exceed configured request cadence;
- worker crash/redelivery, stale queued work, company cascade deletion, and unique active scan behavior;
- all three new permissions, 401/403/404 behavior, CSRF, owner isolation, malformed UUIDs, pagination/filter bounds, and safe validation errors.

### Frontend and browser tests

- service/model/component tests for start, polling, terminal stop, candidates, manual URL, permission controls, error retention, safe rendering, and expired-session retry;
- real Playwright journeys for explicit-URL success against controlled fixture sites, name-only `needs_input` and selection, unsupported/robots/timeout outcomes, two-user isolation, reload persistence, cross-tab logout, and narrow viewport;
- retain all Phase 0–2 browser journeys and unit tests.

### Full gates

Run Ruff, format check, strict mypy, full pytest with PostgreSQL/Redis, ESLint, Angular unit/build, Playwright, Alembic drift, Docker health, pip/npm audit, all runtime-image HIGH/CRITICAL scans including Redis, Gitleaks, and hosted GitHub Actions. No unavailable check is reported as passed.

## 12. Incremental implementation order and local checks

### Step A: migration and scan API

Add models, permissions, schemas, owner-scoped list/detail/start/selection APIs, rate limits, and outbox transaction. Commit as one backend slice.

Local check: start the stack, run `alembic current` and `alembic check`, create a company, call the start endpoint twice, and inspect scan history. Expected: revision `0004_career_discovery`, no drift, the second request returns the same active scan, a foreign user receives 404, and the scan remains safely queued even if Redis is unavailable.

### Step B: safe HTTP boundary and discovery pipeline

Add address-pinned transport, robots/homepage/sitemap inspection, generic link rules, ATS recognition, budgets, and deterministic fixtures.

Local check: run the focused SSRF and pipeline tests. Expected: fixture public routes discover a source; private/mixed/rebinding targets are never contacted; redirects and oversized/slow responses end with the documented safe codes.

### Step C: Redis, dispatcher, and Celery worker

Add dependencies, configuration, Redis/worker/dispatcher Compose roles, outbox delivery, leases, retries, and hostname rate limiting. Commit only after broker-outage and duplicate-delivery tests pass.

Local check: start Compose, stop Redis, create a scan, restart Redis, and watch the persisted scan complete. Expected: the queued row survives, exactly one terminal result is stored, worker restart is harmless, and Redis exposes no host port.

### Step D: Angular scan experience

Add company action, scan history/detail, ambiguity selection, bounded polling, safe states, and frontend tests.

Local check: use controlled fixture companies to start one successful scan and one name-only scan. Expected: the first shows a discovered source, the second asks for selection without contacting a guessed site, reload preserves both, and polling stops after terminal status.

### Step E: full verification and documentation

Run all regression, browser, security, migration, container, and hosted gates; fix defects; record exact counts and links; update ADR/operations/architecture/README and a step-by-step Phase 3 local checklist.

Local check: follow the new checklist from a fresh disposable stack. Expected: all services become healthy, all documented journeys match observed behavior, CI is green, and cleanup removes only the Phase 3 test project/volumes.

## 13. Acceptance criteria

Phase 3 is complete only when:

- explicit website/careers URLs can produce persisted source discovery without job extraction;
- resolved official-site evidence is persisted separately, is traceable to user-supplied or user-confirmed input, and never overwrites the company record automatically;
- name-only input cannot trigger an unconfirmed network request and ambiguous candidates can be selected or replaced by a user URL;
- homepage links, robots-declared/default sitemaps, and the three initial ATS families are recognized through generic rules;
- every outbound connection and redirect passes tested DNS/address pinning and private-network denial;
- scans execute asynchronously through Redis/Celery with durable outbox recovery, idempotent delivery, bounded retries, and hostname rate limits;
- scan lifecycle/results survive reloads and worker/broker restarts in the tested recovery cases;
- owner isolation, database permissions, CSRF, submission limits, safe errors/logs, and resource budgets pass;
- Angular exposes initiation, history, status, candidates, sources, failure/unsupported states, polling cleanup, and responsive behavior;
- migration, regression, dependency, container, secret, browser, and hosted CI gates pass;
- implementation, decisions, operations, local reproduction, limitations, and exact test evidence are documented;
- no Phase 4 extraction, job records, matching, AI, schedules, or notifications are introduced.

## 14. Material tradeoffs and known limitations

- Safe name-only resolution is deliberately weak without an approved search provider. It favors user confirmation over false official-domain claims.
- Hostname-level rate limiting may treat subdomains independently; the scan-wide budget bounds abuse until a reviewed public-suffix strategy is justified.
- Static HTTP discovery will report some JavaScript-only sites as unsupported. Browser rendering belongs to Phase 4 and requires separate SSRF controls for browser requests.
- PostgreSQL outbox plus at-least-once Celery delivery adds one dispatcher role, but it removes the more serious lost-message gap and gives testable recovery.
- Initial ATS recognition is intentionally small and generic. Adding another platform requires fixtures, public-interface review, and the same outbound policy; no company-specific adapter is allowed.
- Company deletion cascades Phase 3 history and sources. Scan history has no separate delete/cancel endpoint in this phase.

Technical references reviewed for the plan include the official HTTPX custom transport/timeouts documentation, Celery task retry/late-ack and Redis broker guidance, Redis atomic rate-limit pattern, Greenhouse Job Board API documentation, and Playwright Python installation/browser lifecycle documentation. Versions will be pinned and locked only after implementation-time compatibility verification; no dependency was changed while preparing this plan.

## 15. Approval boundary

This document is the reviewable Phase 3 plan. No Phase 3 code, migration, dependency, service, or runtime configuration has been added. Implementation begins only after explicit approval, proceeds through the steps above with a local check and expected result reported after each step, and stops before Phase 4.
