# ADR 0003: private companies and validated preference documents

Status: accepted under the approved Phase 2 plan.

## Decisions

Company records are private to their owner. A shared directory would require entity resolution, ownership disputes, and merge policies that are not part of this phase. Names, website URLs, and externally hosted careers URLs are user-supplied and explicitly unverified. A hostname-derived display label is a fallback, not a claim about a legal company name.

Duplicates use an owner-scoped SHA-256 key over canonical website URL, otherwise canonical careers URL, otherwise normalized name, with a source prefix. Database uniqueness covers concurrent writes. HTTP/HTTPS, different paths, and name-only versus URL-backed entries are deliberately not merged. Different users can save identical records without learning about one another.

URL input validation is pure: no DNS or HTTP. It requires HTTP(S), a DNS hostname, and the scheme's standard port; rejects credentials, fragments, IP literals, local/reserved suffixes, invalid IDNA, controls, malformed escapes, and ambiguous authorities; and preserves meaningful paths/queries. IDNA uses the pinned Python standard library's codec consistently. This policy is not SSRF authorization. Phase 3 must validate actual destinations, DNS results, and redirects at fetch time.

Preference profiles are a separate aggregate from account profiles. They combine relational ownership/name/creation metadata with a typed JSONB criteria document. These documents are loaded and replaced as a whole; taxonomy tables and searchable child rows would add complexity without a Phase 2 query requirement. A new dictionary is assigned on each update so SQLAlchemy persists nested edits. An owner-scoped hash of the normalized name prevents duplicate profile names without a database key-length dependency on Unicode normalization expansion.

Criteria are user-defined strings, with explicit bounds, Unicode-aware comparisons, and preserved punctuation. No skill, company, job-title, location, or employment catalog is embedded. Work-arrangement states and six weight-factor keys are schema contracts. Weights are user-allocated strict integers totaling 100 and persist with the profile; there are no business-weight defaults or matching scores. Positive weights need configured criteria. Exact conflicts are rejected; no semantic synonym inference is performed.

PUT replaces a complete editable document, avoiding ambiguous partial array merges. Updates use last-write-wins, consistent with the existing profile API. Two editors can overwrite each other's changes; optimistic concurrency remains a documented limitation. Deletes are explicit and confirmed in the UI. Later scan/history phases must revisit deletion references before adding them.

## Security and integration

Eight new permission contracts cover read/create/update/delete for each resource. The migration grants them only to the existing seeded member role. Custom roles remain unchanged. Every resource query includes the authenticated owner; foreign and nonexistent IDs produce indistinguishable 404 responses. Extra ownership/internal fields are rejected. CSRF protection now explicitly includes PUT JSON mutations.

Private responses are non-cacheable. New form errors contain at most 24 allowlisted field paths/codes, never raw values, exception context, or SQL. Credential errors retain the Phase 1 format. Angular extends the existing guarded routes, refresh interceptor, fresh-CSRF retry, allowed return paths, and cross-tab logout behavior. It does not automatically retry ambiguous network failures or store form drafts in browser storage.

No dependency changes, additional infrastructure, HTTP fetching, scanners, matching logic, or Phase 3 functionality were needed. Shared test fixtures moved to `conftest.py` with reusable credential helpers; existing security tests remain active.
