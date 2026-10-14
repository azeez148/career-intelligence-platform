# ADR 0005: ordered, SSRF-safe job extraction with an isolated browser stage

Status: accepted for Phase 4.

## Context

Phase 3 identifies career sources but stores no jobs. Sources range from ATS boards with documented public APIs to static pages, pages with schema.org data, and pages that only render listings with JavaScript. Every outbound request, including browser sub-requests, must keep the Phase 3 SSRF, robots, rate, and budget guarantees. Extracted data must never be invented, and extraction must survive retries and redelivery.

## Decision

**Separate runs.** Each source gets `extraction_runs` rows with their own outbox, lease, bounded retries, and terminal state. Discovery success queues one run per source in the same transaction; users can re-run one source (rate-limited per user and per source). One failing source never fails its scan.

**Strategy order.** The runner stops at the first strategy that yields jobs:

1. Greenhouse Job Board and Lever Postings public APIs (`high` confidence), including boards embedded on company pages.
2. schema.org `JobPosting` JSON-LD on the source page or on detail pages (`medium`).
3. Repeated same-host job-link groups with bounded pagination and detail pages (`low`).
4. Browser rendering, only when 1–3 found nothing and the page looks script-rendered (little visible text and scripts present). The run moves to a `browser` stage on its own queue.

Workday has no documented public job API, so it is handled only through public pages. The browser stage blocks non-GET requests, so sites that load listings by POST (including Workday's own frontend) are reported unsupported rather than called directly.

**Normalization.** One `jobs` model with title, location text, work mode, employment type, department, plain-text description and requirements, dates, and provenance (`extraction_method`, `confidence`, per-field `field_sources`). Values map only from exact vocabulary; anything else stays `unknown` or `NULL`. Requirements come only from explicitly labelled sections or structured fields. HTML is reduced to bounded text; scripts, styles, and markup are never stored.

**Identity and lifecycle.** `dedupe_key` is `<platform>:<id>` for ATS jobs and the canonical URL otherwise; postings that share a listing page URL are keyed by their identifier or fingerprint. Cross-source copies with the same normalized title and location are linked through `duplicate_of_job_id` to the highest-confidence copy and hidden by default. Jobs missing from a complete run are closed; partial runs never close jobs. `extraction_run_jobs` records which runs observed each job and how it changed.

**Browser isolation.** A separate Debian image (Playwright publishes glibc builds only) runs the Chromium headless shell with only the libraries it links against, read-only, non-root, with memory and process limits. Every request from the page is intercepted. It is fulfilled through `SafeHttpClient` and the shared robots policy, or aborted. Non-GET methods, cross-site hosts (outside the source's parent domain), WebSockets, service workers, downloads, and images/media/fonts are blocked, and requests and time are budgeted. Chromium is launched with an unreachable proxy and no loopback bypass, so anything that escapes interception fails closed. The start document's redirect chain is resolved through the policy before navigation, because Chromium cannot follow a fulfilled 3xx navigation.

**Test-only fixture access.** `OUTBOUND_TEST_HOSTS` maps exact hostnames to fixture containers so the isolated stack can run real discovery-to-jobs journeys. Settings reject it in production and only `compose.test.yaml` sets it. The connected peer is still pinned to the resolved address.

**Image-scan gate.** The API, web, database, and Redis images keep the strict HIGH/CRITICAL gate. With the user's approval, the browser image fails CI only on HIGH/CRITICAL findings that have a fixed version (`--ignore-unfixed`), and an informational step lists the rest. At adoption it had 61 unfixed findings, 48 of them inherited from the official `python:3.13.16-slim-trixie` base image.

## Alternatives considered

- **Extending the scan lifecycle with extraction states.** Rejected: it couples source failures to discovery history and blocks per-source retries.
- **Calling Workday's undocumented frontend JSON endpoint.** Deferred: it needs a terms review. A separate adapter can be added later.
- **Running Chromium in the Alpine image.** Not possible: Playwright publishes no musl wheels or browser builds.
- **Blocking all cross-host browser requests.** Breaks most sites that serve assets from a sibling subdomain. Allowing the source's parent domain keeps CDN-on-another-company setups unsupported rather than widening egress.
- **Keeping API-mocked browser tests.** This is how a Phase 3 worker defect escaped notice, so the stack now runs real journeys against fixture sites.

## Consequences

- Heuristic listings will miss or mis-group some sites; they are labelled `low` confidence and empty results are reported as `no_jobs_recognized`.
- The browser image is large (about 1.1 GB) and must be rebuilt regularly to pick up Debian fixes.
- Jobs are stored per owner because companies are per owner.
- Job descriptions are untrusted text and must be treated as data, never instructions, if Phase 5 sends them to an AI provider.
