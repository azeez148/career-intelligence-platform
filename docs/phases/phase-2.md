# Phase 2: company and preference management

Status: complete following explicit approval. Local checks and all four [hosted CI jobs](https://github.com/azeez148/career-intelligence-platform/actions/runs/38561810158) passed for final implementation commit `fe83d8f`. Phase 3 has not begun.

## Implemented

- Private company CRUD from name, website, or careers URL; canonical input validation, deterministic owner-scoped duplicate handling, and unverified-source display.
- Multiple named preference profiles with user-defined skills, keywords, titles, seniority, locations, employment types, remote policy, experience bounds, and persisted user-allocated matching weights.
- Database permission dependencies and owner-scoped queries for every read/write/delete; CSRF JSON protection for PUT; safe bounded form-validation errors.
- Angular list/editor screens, confirmations, empty/loading/error states, preserved rejected form input, pagination, permission controls, allowed return URLs, expired-session recovery, and logout across the new routes.
- Migration `0003_companies_preferences`, eight new permissions, preservation of Phase 1 data, and shared test fixture reuse.

## Files and contracts

New backend files live in `app/modules/companies/`, `app/modules/preferences/`, `core/urls.py`, `core/values.py`, and `core/form_errors.py`. Composition, model registration, error handling, CSRF checks, and regression assumptions were updated. New tests cover URLs, companies, preferences, and migration preservation; existing authentication tests share extracted fixtures/helpers.

New frontend files live in `src/app/companies/`, `src/app/preferences/`, and `resource-errors.ts`; shell/routes/auth integration and styles were updated. `e2e/companies-preferences.spec.ts` exercises the real database-backed flows. No runtime dependencies or infrastructure services were added.

API contracts and database/security behavior are described in [operations](../operations/company-preferences.md), and design alternatives in [ADR 0003](../decisions/0003-companies-preferences.md). The approved [plan](phase-2-plan.md) records the acceptance matrix. Exact verification evidence is in [testing](../testing/phase-2.md); [local checks](../testing/phase-2-local-check.md) explain commands/actions and expected results after each step.

## Limitations and stop condition

No domain resolution, website verification, HTTP fetching, discovery, scanning, job data, matching scores, AI, or queues are implemented. Company identity deduplication is exact-input based, not entity resolution. URLs using IP hosts/non-standard ports are unsupported. Lists have bounded offset pagination. Edits use last-write-wins. Custom roles require explicit grants for new capabilities.

Phase 3 may reuse these owned resources and preference documents, but must independently enforce request-time SSRF defenses and design scan/history deletion behavior. Stop after Phase 2 acceptance; Phase 3 requires a separate approved plan.
