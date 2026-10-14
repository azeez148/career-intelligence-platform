# Phase 2 plan: company and preference management

Status: explicitly approved by the user; implementation in progress.

## 1. Inspection and scope

Reviewed `MASTER_PLAN.md` completely and inspected the repository at `8c28461`, with a clean working tree before this plan. Phase 1's final [CI run](https://github.com/azeez148/career-intelligence-platform/actions/runs/38553525433) passed. Recorded baseline: 31 backend tests, 15 Angular tests, five browser journeys, strict checks, dependency audits, and image/secret scans.

The modular monolith already supplies async SQLAlchemy sessions, Alembic, UUID users, database permissions, CSRF helpers, sanitized errors, Angular Reactive Forms/guards, cookie refresh, and disposable PostgreSQL/browser tests. Reuse those components and the current locked dependencies.

| Phase 2 requirement | Repository gap and planned remedy |
|---|---|
| Company creation and identity | No company module/table; add private user-owned saved company records with explicit duplicate semantics |
| Website/careers URLs | No resource URL validator; add strict parsing/normalization, without network requests or verification claims |
| Multiple preference profiles | Account profile is only display name/bio; add a separate preference aggregate and full CRUD |
| Skills, keywords, titles, seniority, locations, employment, experience | No preference schema; add bounded user-defined values and cross-field validation |
| Configurable weights | No persisted weights; require explicit per-profile allocations and validate them |
| Ownership and permissions | Reuse permission dependencies; seed new permission contracts and owner-scope every query |
| Angular management | Add list/editor screens; extend session refresh, return-path handling, and logout redirects for their routes |
| Tests/docs | Add feature/URL tests, upgrade-preservation tests, browser workflows, and per-step local instructions |

Deliverable: authenticated users can manage their own companies and multiple named preference profiles, with validated inputs and persisted settings.

Excluded: domain resolution from company names, website ownership verification, DNS lookup, HTTP fetching, careers discovery, scanning, queues, Redis/Celery, job extraction, matching scores, AI, scheduling, shared company directories, administrative taxonomies, and company-to-profile assignment. A future scan can select a company and a preference profile; Phase 2 does not need a linking table.

## 2. Company behavior and URL decisions

### Ownership and identity

- Each saved company belongs to exactly one authenticated user. Identical records owned by different users are allowed and never expose one another's data.
- Create accepts `name`, `website_url`, and `careers_url`, each optional individually; at least one must be present. A name-only record is valid and remains unresolved. A careers-only record supports the master-plan entry flow without guessing a website.
- Store a supplied name as user input. If absent, return a computed display label based on the supplied URL hostname; do not present that hostname as a verified legal/company name.
- Name limit: 200 characters after trimming/collapsing whitespace. URLs: at most 2,048 characters before and after normalization. Reject blank supplied values; the UI submits absent optional fields as null.
- One manually supplied website URL and one manually supplied careers URL per company in this phase. The careers hostname may differ from the website hostname because careers can be hosted externally. No same-domain requirement or provider-specific exception list.
- Duplicate identity is deterministic and owner-scoped: canonical website URL when present, otherwise canonical careers URL, otherwise normalized name. Use a source prefix and SHA-256 identity key plus a database unique constraint on `(user_id, identity_key)`; derive the key server-side. Unique-conflict handling covers concurrent creates/updates. Do not accept an identity key or owner ID from clients.
- A duplicate returns 409 and a stable code, never an unhandled constraint error. The same name on different URLs is allowed. Name-only and URL-backed records are not automatically merged, and HTTP/HTTPS, `www`/non-`www`, or different paths are not assumed to identify the same company. Explain these limits in the UI/docs.
- Edit validates the final complete record and recomputes its identity. Delete removes the owned record after a UI confirmation. There are no scans/jobs to preserve in Phase 2; later phases must review deletion dependencies.

### URL validation and security boundary

- Require an explicit absolute `http://` or `https://` URL. Reject credentials, fragments, missing hosts, unsupported schemes, raw whitespace/control characters, backslashes, malformed escapes, invalid hostname/port syntax, and ambiguous numeric-host forms.
- Permit only the scheme's standard port (80 for HTTP, 443 for HTTPS); remove explicit default ports during canonicalization. Non-standard-port sources are an explicit Phase 2 limitation.
- Normalize scheme and DNS hostname case, encode internationalized hostnames consistently, remove a terminal DNS dot, and use `/` for an empty path. Preserve path case and query meaning/order; do not strip arbitrary tracking parameters, collapse company paths, or rewrite escaped delimiters.
- Reject IP-literal hosts entirely for this first company-source interface, along with localhost, single-label hosts, and explicit local/internal/reserved host suffixes. This is a generic input policy, not a list of approved company domains. Test IPv4, IPv6, mapped addresses, encoded authority delimiters, alternate numeric notations, and trailing-dot variants.
- No DNS resolution, redirect following, or outbound HTTP occurs during save/list/edit. A syntactically acceptable hostname can still resolve privately; stored URLs are **unverified inputs**, not evidence of SSRF safety or website ownership.
- Phase 3 must independently validate DNS results, destinations, and every redirect at request time, including rebinding defenses. Never treat Phase 2 validation as permission to fetch a URL.
- Display links as text in this phase; do not automatically navigate, embed previews, or fetch favicons. Never log full URLs or preference contents.

Python's URL parser explicitly does not validate inputs, so application validation must precede/use parsing deliberately rather than accepting a successfully parsed value. [Python URL parsing security](https://docs.python.org/3.13/library/urllib.parse.html#url-parsing-security).

## 3. Preference contract and validation

Preference profiles are separate from the account's display-name/bio profile. Users can create multiple profiles, each with an owner-scoped unique normalized name (1–100 characters).

Store a typed preference document in PostgreSQL JSONB, with relational owner/name/timestamps. No generic arbitrary JSON editor or unvalidated dictionaries. JSONB fits a bounded document read/written as a whole; no array-search indexes or taxonomy tables are needed before matching exists. Assign a newly validated document on updates so SQLAlchemy detects nested changes reliably.

| Field | Representation and rule |
|---|---|
| `preferred_skills` | User-defined string list |
| `required_skills` | User-defined string list, separate from preferred skills |
| `preferred_keywords` | User-defined string list |
| `excluded_keywords` | User-defined string list |
| `job_titles` | User-defined string list; no hardcoded title catalog |
| `seniority_preferences` | User-defined string list; no hardcoded seniority catalog |
| `locations` | User-defined string list; no city/country catalog or geocoding |
| `remote_policy` | `any`, `remote_only`, or `exclude_remote`; these are behavior states, not geographic values |
| `employment_types` | User-defined string list; no fixed industry/customer taxonomy |
| `experience_min_months`, `experience_max_months` | Optional strict integers, 0–1,200 inclusive; min must not exceed max when both supplied |
| `weights` | Six required strict integer fields: `skills`, `title`, `location`, `experience`, `employment`, `keywords`; each 0–100, total exactly 100 |

Normalize comparison keys using Unicode normalization, case-folding, and collapsed whitespace while preserving readable display text. Preserve meaningful punctuation such as `+`, `#`, and `/`. Each list is limited to 50 items, each item to 100 characters, and all lists combined to 200 items. Reject empty or duplicate normalized entries; do not silently discard conflicting user choices.

Cross-field rules:

1. Reject overlap between required and preferred skills; a skill must be assigned one importance category.
2. Reject exact normalized overlap between excluded keywords and preferred keywords, required skills, preferred skills, or desired titles. Do not invent synonym, substring, or semantic conflict detection.
3. `remote_only` can coexist with locations: geographic restrictions still matter for remote roles. Do not infer visa, travel, or relocation eligibility.
4. A positive weight requires criteria for that factor: skills lists; titles/seniority; locations or a non-`any` remote policy; an experience bound; employment types; or preferred keywords, respectively. Exclusions alone are filters, not positively weighted criteria.
5. Require at least one positively weighted configured factor. Unknown weight keys, missing keys, booleans, numeric strings, non-finite numbers, fractional/negative values, and totals other than 100 are rejected.
6. Weights apply only to soft matching factors. Required skills, exclusions, and remote restrictions are stored distinctly; Phase 5 defines their execution. Phase 2 produces no match score or hiring probability.

Do not embed default skills, locations, titles, companies, or numerical scoring weights in the frontend/backend. New forms begin with empty criteria and unallocated weights; the user chooses an allocation before saving. Factor names are a stable application schema, while selected values and all weight allocations persist per profile in PostgreSQL.

Use bounded, allowlisted validation details for these new forms where needed: field paths plus stable error codes, without echoing entered values, Pydantic contexts, SQL, or exception text. Preserve Phase 1's generic handling of credential validation and errors. Prefer local schema/cross-field validators and focused domain errors to a global error-format rewrite.

## 4. Database and authorization changes

Create one explicit migration, `0003_companies_preferences.py`, after `0002_identity_profiles_rbac`.

| Table | Columns/constraints |
|---|---|
| `companies` | UUID PK; user FK with cascade; nullable name/website_url/careers_url; derived identity key; UTC created/updated times; at-least-one-input check; unique `(user_id, identity_key)`; owner/list ordering index |
| `preference_profiles` | UUID PK; user FK with cascade; name and normalized name key; JSONB criteria document; UTC created/updated times; unique `(user_id, name_key)`; JSON-object check; owner/list ordering index |

Document-level invariants are enforced by the typed API/service, not duplicated as complex PostgreSQL JSON-validation functions. Relational uniqueness, ownership references, non-nullness, and basic shape checks remain database-enforced. Updates use last-write-wins, matching the existing profile API; optimistic versioning is not added in this phase.

Seed eight permission codes: `companies:{read,create,update,delete}:self` and `preferences:{read,create,update,delete}:self`. Grant them to the existing seeded member role. Do not recreate deleted roles or silently grant permissions to custom roles; operators must explicitly assign new capabilities to customized roles. Controllers depend on permission codes, not role names.

Every resource query includes both resource ID and current user ID. Unknown and other-owner IDs return the same 404. Unauthenticated requests return 401; missing permissions return 403. Clients cannot supply/change owner IDs, internal keys, timestamps, or role assignments. Mutation requests retain signed CSRF, allowed-Origin, and JSON protections. Lists are private and non-cacheable.

Migration verification must seed real Phase 1 user/profile/session and customized RBAC state before upgrading, then prove it survives. Repeated upgrade must not duplicate seed rows. Downgrade removes only Phase 2 tables and permission assignments/codes; Phase 1 account data remains. Downgrade destroys Phase 2 data and is only exercised on disposable databases. Verify re-upgrade and `alembic check` afterward.

## 5. API contracts

All routes below are under `/api/v1`. Use thin routers, focused services with explicit transaction boundaries, existing dependencies, and the established error envelope.

| Method/path | Contract |
|---|---|
| POST `/companies` | Create from name/website/careers input; 201 public owned company |
| GET `/companies` | Own companies, `limit` 1–100 (default 20), bounded offset; `{items,next_offset}` |
| GET `/companies/{id}` | Own company detail; 200 or 404 |
| PUT `/companies/{id}` | Replace editable name/website/careers fields; 200; clear optional fields explicitly with null |
| DELETE `/companies/{id}` | Delete own company; 204 or 404 |
| POST `/preferences` | Name plus complete criteria/weights; 201 owned profile |
| GET `/preferences` | Own profile summaries with the same bounded pagination |
| GET `/preferences/{id}` | Complete owned preference profile |
| PUT `/preferences/{id}` | Replace name and complete validated preference document; 200 |
| DELETE `/preferences/{id}` | Delete own preference profile; 204 or 404 |

Use stable ordering by creation time plus UUID. Return identifiers, editable fields, and timestamps, but not internal identity/name keys. Company responses include the computed display label and an explicit indication that URLs are unverified. List summaries avoid transferring all preference arrays until the editor/detail is opened.

PUT is deliberate: validating one complete document avoids ambiguous array merging and cross-field validation of partially updated preferences. The editor loads the current record and submits the complete editable representation. No bulk endpoints, search indexing, filters, admin APIs, or automatic retries for ambiguous network failures.

Errors: 401 authentication; 403 permission/CSRF; 404 not found/not owned; 409 duplicate company/profile name; 422 invalid input/conflict/weights. No raw input echoes in error responses or logs.

## 6. Angular integration

Add standalone list/editor components and typed HttpClient services under `src/app/companies/` and `src/app/preferences/`. Reuse Reactive Forms, existing styles, and auth state/guards; no UI library or state-management dependency.

Routes: `/companies`, `/companies/new`, `/companies/:id/edit`, `/preferences`, `/preferences/new`, `/preferences/:id/edit`. Register `new` before parameterized routes. Add permission-aware navigation and create/edit/delete controls; backend enforcement remains authoritative.

Company forms provide separate labeled name, website, and careers fields, duplicate/invalid-URL messages, and visible unverified-source wording. Preference forms group skills, keywords, job criteria, locations/work arrangement, experience, and weights. Use one item per line for user-defined lists to preserve commas/punctuation within values; provide explicit item-count/length guidance. Display weight allocation total and actionable validation messages.

Provide loading, empty, saved, not-found, forbidden, network-failure, and retry states; accessible labels/focus/error associations; destructive-action confirmation; disabled controls while saving. Preserve unsaved form values on rejected saves. Do not persist sensitive form drafts to browser storage.

Required changes to existing Phase 1 integration discovered during inspection:

- `auth.interceptor.ts`: add exact new API prefixes to protected-request detection; retain one refresh/retry on 401, no refresh on 403, and updated CSRF headers on mutation retries.
- `auth.service.ts`: extend safe return destinations to only supported local company/preference routes, including UUID edit paths; continue rejecting external/protocol-relative/malformed destinations.
- `app.ts`: recognize the new protected routes for cross-tab logout redirects.
- `app.routes.ts` and `app.html`: lazy routes and navigation with permission contracts.
- `main.py`: extend private-response `no-store` treatment to companies/preferences; preserve sanitized failures and existing health behavior.

## 7. File plan

Create after approval:

- `apps/api/app/modules/companies/{__init__,models,schemas,service,router}.py`.
- `apps/api/app/modules/preferences/{__init__,models,schemas,service,router}.py`.
- `apps/api/app/core/urls.py`: pure reusable validation/canonicalization; no HTTP client or DNS resolver.
- `apps/api/migrations/versions/0003_companies_preferences.py`.
- `apps/api/tests/test_companies.py`, `test_preferences.py`, `test_urls.py`, and a focused Phase 1-to-2 migration-preservation test.
- `apps/web/src/app/companies/`: typed API service, list/editor components, and tests.
- `apps/web/src/app/preferences/`: typed API service, list/editor components, validators, and tests.
- `apps/web/e2e/companies-preferences.spec.ts`.
- `docs/decisions/0003-companies-preferences.md`, `docs/phases/phase-2.md`, `docs/testing/phase-2.md`, `docs/testing/phase-2-local-check.md`, and `docs/operations/company-preferences.md`.

Modify:

- API model registry/router/composition and narrowly scoped error support if required for safe form error codes.
- Existing test fixtures as needed to reuse disposable database helpers without hiding database reset behavior; update hardcoded migration-head/table expectations and add seed-preservation assertions.
- Angular shell/auth files listed above and regression tests; shared styles only where the new forms need them.
- README and architecture documentation. Existing CI test discovery should automatically include new suites; change CI only if a concrete new gate needs a command. Compose/security settings remain the working foundation.

No dependency upgrade is planned. If implementation demonstrates a dependency gap, review compatibility and necessity before changing a lockfile; do not opportunistically update the stack.

## 8. Implementation sequence and local checks after each step

After each completed implementation step, report **what changed**, **the exact local command or browser action**, and **the expected result**, as requested. These are future verification steps, not claims that Phase 2 currently exists.

| Step | Work | Local check and expected result after implementation |
|---|---|---|
| 1 | Add models, migration, and permissions | `docker compose up --build -d --wait`; `docker compose exec api .venv/bin/alembic current` shows `0003_companies_preferences`; existing login/profile still work |
| 2 | Add company validation/services/API | From `apps/api`, `uv run --no-sync pytest -q tests/test_urls.py tests/test_companies.py`; valid name/URLs pass, duplicates/unsafe inputs/foreign ownership fail with expected codes |
| 3 | Add preference document validation/services/API | `uv run --no-sync pytest -q tests/test_preferences.py`; multiple profiles persist; invalid bounds/conflicts/weight totals fail |
| 4 | Add company screens and auth integration | Rebuild Compose, open `http://127.0.0.1:8080/companies`; create, reload, edit careers URL, attempt duplicate, delete; each action shows its expected state |
| 5 | Add preference screens | Open `/preferences`; create two differently named profiles, edit criteria/weights, reload, delete one; the other remains unchanged; invalid allocations do not save |
| 6 | Verify security and regressions | Run full backend/frontend checks and isolated Playwright stack; another browser account cannot see/edit the first account's data; refresh and logout still work on new routes |
| 7 | Document, commit/push, and verify hosted CI | Publish exact test results and local guide; inspect all hosted CI jobs for the final implementation; stop before Phase 3 |

Full backend gates from `apps/api`: Ruff lint/format, mypy, pytest including Testcontainers, and pip-audit. Frontend gates from `apps/web`: `npm run lint`, `npm test`, `npm run build`, `npm audit --audit-level=high`. Use the existing isolated Compose/Playwright arrangement, update the local guide for a clearly named Phase 2 test project, and preserve the normal development database when cleaning up.

## 9. Test and acceptance matrix

| Area | Required proof |
|---|---|
| Company CRUD | Name-only, website-only, careers-only, edits/clearing optional fields, bounded pagination, delete, malformed UUIDs, blank/oversized input, unknown fields |
| Duplicates | Normalized-equivalent inputs; concurrent create/update conflict; identity changes after edits; same record allowed for different users; distinct paths/hosts not silently merged |
| URL policy | Scheme/credentials/port/hostname/path/query cases, internationalized hosts, raw/encoded controls, alternate numeric IP forms, IPv6, local/internal suffixes, no network/DNS calls |
| Preferences | Multiple independent profiles, name uniqueness, strict types/list bounds, Unicode/punctuation preservation, empty/duplicate values, overlaps, experience ranges, remote/location combinations |
| Weights | Exactly six keys, strict integer bounds, total 100, at least one configured positive factor, positive allocation without criteria rejected, valid settings survive reload |
| Security | 401/403/404 semantics, all mutations protected by CSRF, owner-scoped list/read/write/delete, forbidden owner/role injection, no cross-user duplicate leakage, no raw inputs in errors/logs |
| Migration | Phase 1 data and custom assignments survive upgrade; repeat upgrade; Phase 2-only downgrade preserves accounts; re-upgrade; no metadata drift |
| Angular | List/editor validation, loading/empty/error states, permission controls, safe return routes, expired-access refresh on new GET/PUT requests, one retry with fresh CSRF, cross-tab logout |
| Playwright | Real company/preference CRUD, duplicates and rejected forms, two profiles, reload persistence, two-user isolation, revocation/session recovery on new routes, responsive forms |
| Regression/CI | All Phase 0/1 tests retained, updated migration expectations only where necessary, Docker startup, strict builds/lint/types, audits, all three runtime scans, secret scan, hosted CI |

Acceptance requires all master-plan Phase 2 features and gates above, documented outcomes/limitations, no blocking defects, and no Phase 3 functionality. Tests unavailable due to environment constraints must be marked NOT VERIFIED, never passed or silently skipped. Record new test counts from actual runs rather than inventing a target.

## 10. Documentation, tradeoffs, and approval boundary

The ADR will explain private company ownership versus a global directory, exact-input duplicate keys versus entity resolution, JSONB preference documents versus taxonomies/child tables, full replacement versus patch merging, user-allocated weights versus hardcoded defaults, and why URL persistence does not prove safe future network access.

Operations docs will cover permission rollout to customized roles, explicit URL/port limitations, unresolved company identities, unverified sources, last-write-wins edits, data deletion, migration rollback risks, and isolated test cleanup. The phase report will list files changed, API/database changes, test evidence, security results, outstanding limitations, and the Phase 3 dependency boundary.

**Approval requested for this plan only. Implementation starts after explicit approval of Phase 2.** After implementation and verification, stop before Phase 3.
