# Phase 4: job extraction and normalization

Status: implemented and locally verified on 2026-10-14/15. Hosted CI has not run because the commits are not pushed (the Phase 3 hosted gate is also still pending). Phase 5 has not started.

## What was implemented

- **Extraction runs** per career source, queued automatically when discovery succeeds and manually from the scan page. They have their own outbox, leases, bounded retries, and rate limits.
- **Strategies in the approved order:**
  1. Greenhouse and Lever public APIs, with Lever pagination and boards embedded on company pages.
  2. schema.org JSON-LD.
  3. Generic static listings with pagination and detail pages.
  4. Browser rendering in an isolated worker for script-rendered pages.
- **One normalized job model** with confidence, per-field provenance, dedupe keys, cross-source duplicate linking, run observations, and closing after complete runs.
- **API:**
  - `GET /api/v1/jobs` with filters for company, source, text, work mode, employment type, open/closed status, and duplicates;
  - `GET /api/v1/jobs/{id}`, `GET /api/v1/extractions/{id}`, and `POST /api/v1/sources/{id}/extractions`;
  - per-source extraction summaries on `GET /api/v1/scans/{id}`.
- **Angular:** an extraction panel on the scan detail page, the `/jobs` explorer, and `/jobs/:id` detail. Descriptions render as text, and missing values show as "Not stated".
- **Migration** `0005_job_extraction` with permissions `jobs:read:self` and `extractions:create:self` for members.

Design rationale is in [ADR 0005](../decisions/0005-job-extraction.md), operating procedures in [job extraction operations](../operations/job-extraction.md), and evidence in [Phase 4 verification](../testing/phase-4.md). The approved plan is in [phase-4-plan.md](phase-4-plan.md).

## Approved decisions

1. Separate extraction runs.
2. A separate Debian browser-worker image.
3. Workday through public pages only.
4. A test-only fixture host allowlist.
5. **Approved during implementation:** the browser image fails CI only on HIGH/CRITICAL findings that have a fix. All other images keep the strict gate.

## Deviations from the plan

- Python Playwright is pinned to **1.63.0**, not the two-day-old 1.64.0.
- Browser task limits are **170 s / 180 s** instead of 120 s / 130 s, and the browser stage has a run-wide budget of 240 responses / 40 MiB. This allows one listing render plus up to three detail renders.
- **Cross-site browser requests are allowed only within the source's parent domain.** The plan said "a different host is blocked"; blocking every other host breaks sites that serve assets from a sibling subdomain.
- **The real end-to-end journeys cover JSON-LD, static, and browser sources.** The Greenhouse and Lever API paths are covered by offline fixture tests only, because their fixed HTTPS hosts cannot be served by a local fixture container.

## Known limitations

- Static and browser listings are heuristic and `low` confidence. Sites that load jobs by POST, through login, or from another company's CDN are reported unsupported.
- Exact-host rate limiting still treats subdomains independently.
- Jobs are stored per owner.
- Nginx resolves `api` once at startup, so restart `web` after recreating only `api`.
- The browser image carries unfixed Debian findings (61 at adoption) and needs regular rebuilds.
- Celery's own per-task success lines don't appear in worker logs, because the app's logging setup replaces Celery's handlers. Use run status in PostgreSQL instead.

## Next-phase dependencies

Phase 5 matching reads `jobs` (open, non-duplicate) and preference profiles. It must treat `description_text` and `requirements_text` as untrusted data if any AI provider sees them, and should use `confidence` and `field_sources` to explain missing or inferred information.
