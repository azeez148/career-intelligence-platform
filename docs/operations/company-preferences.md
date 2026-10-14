# Company and preference operations

## Upgrade and permissions

Use the existing `.env` and Compose setup. Rebuild/start with `docker compose up --build -d --wait --wait-timeout 180`. The migration service applies `0003_companies_preferences` before API readiness succeeds. Check with `docker compose exec api .venv/bin/alembic current` and `docker compose exec api .venv/bin/alembic check`.

The migration creates `companies` and `preference_profiles`, plus `companies:{read,create,update,delete}:self` and `preferences:{read,create,update,delete}:self` permissions. Existing seeded members receive these capabilities. Existing custom roles receive no automatic grants. Review and assign the specific needed permission IDs through an authorized database operation; there is no public role-administration API. A deleted member role is not recreated.

Permission changes take effect on the next backend request. Refresh/reload browser account state to update cached navigation. A user may receive a 403 from an API even if an old screen still shows its action; backend authorization is authoritative.

## API and data behavior

Both `/api/v1/companies` and `/api/v1/preferences` expose POST and paginated GET. Their `/{uuid}` routes expose GET, full-replacement PUT, and DELETE. Lists accept limit 1–100 (default 20) and offset 0–100000. They return `{items,next_offset}` with stable ordering. Preference lists return summaries, and detail reads return criteria.

Company input contains nullable `name`, `website_url`, `careers_url`; at least one is required. Input/output URLs are bounded to 2,048 characters. Name-only records remain unresolved; careers URLs may use another host. Responses include `display_label`, `source_status: unverified`, IDs, and timestamps, but not owner/internal keys. Only standard HTTP/HTTPS ports and DNS hosts are accepted. URLs are displayed as text and never fetched. Some legitimate non-standard-port sources cannot be saved under this phase's conservative policy.

Preference input is `{name,criteria}`. Criteria include preferred/required skills, preferred/excluded keywords, titles, seniority, locations, employment types, remote policy, optional experience bounds in months, and six explicit weights. Each list has at most 50 entries of 100 characters, with 200 entries overall. Profile names are owner-unique after normalization. The API rejects duplicate or conflicting list entries; the UI treats blank textarea lines as separators and omits them.

Weights require all six keys (`skills`, `title`, `location`, `experience`, `employment`, `keywords`), strict integers from 0 to 100, and total 100. A positive factor needs criteria. Experience bounds are optional strict integers from 0 to 1,200, ordered minimum to maximum. Remote-only and locations can coexist. These settings are stored for later matching; no scoring or search is executed.

Error status meanings: 401 authentication, 403 permission/CSRF, 404 absent/not-owned record, 409 duplicate identity/name, 422 invalid values/conflicts. New validation errors include bounded safe `issues` codes; no input values are reflected. Save failures retain form input. Network failures do not establish whether a write committed: reload before retrying an uncertain save. Full replacements use last-write-wins.

## Safety, rollback, and cleanup

Stored company URLs remain unverified, including hostnames that could resolve to private addresses. Do not introduce a fetcher that assumes these rows have passed DNS/rebinding/redirect checks. That belongs to separately approved Phase 3 work.

Deletes are permanent in Phase 2 and operate only on the owner's company/profile. A phase downgrade to `0002_identity_profiles_rbac` removes both new tables and the eight permission codes/assignments. It preserves Phase 1 accounts, profiles, sessions, and prior/custom assignments, but destroys all Phase 2 data. Back up before a real rollback; downgrade tests run only in disposable PostgreSQL containers.

Use a clearly separate `career-phase2-test` Compose project for browser tests. Its database is tmpfs and disposable. Never run its `down --volumes` cleanup against the regular development project. See the [local checklist](../testing/phase-2-local-check.md).
