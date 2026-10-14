# Check Phase 2 locally after each step

Run root commands from the repository root. Start Docker Desktop with Linux containers. Use the existing `.env`; if creating a new checkout, follow [Phase 1 setup](phase-1-local-check.md#1-configure-and-start-the-application) for database credentials, three independent secrets, development mode, and exact local origins. Do not overwrite or commit existing secrets.

## 1. Database migration and existing accounts

```powershell
docker compose up --build -d --wait --wait-timeout 180
docker compose exec api .venv/bin/alembic current
docker compose exec api .venv/bin/alembic check
```

Expected: services are healthy, revision `0003_companies_preferences` is current, and Alembic reports no new upgrade operations. Open <http://127.0.0.1:8080>, sign in with an existing account (or register), and verify its profile still works. Seeded members see **Companies** and **Preferences**; custom roles need explicit new grants.

## 2. Company validation and CRUD

Open **Companies → Add company**. Save a name-only record. Edit it to add an HTTP(S) website and a careers URL (a different hostname is allowed). Reload the list.

Expected: the record and URLs persist; the screen says unverified. No website is fetched. Try adding the same canonical website again: it should show a duplicate error. A localhost/IP URL, credentials, fragment, or non-standard port should be rejected. Editing a URL changes its exact-input duplicate identity; it does not verify the company. Delete the record and accept the confirmation; it should disappear.

Automated proof from `apps/api`:

```powershell
uv run --no-sync pytest -q tests/test_urls.py tests/test_companies.py
```

Expected: URL parsing/normalization, no-DNS behavior, ownership, all permissions, and concurrent uniqueness tests pass.

## 3. Preference validation and multiple profiles

Open **Preferences → Add preference profile**. Enter a name and one or more skills, one item per line. Allocate 100 to Skills and zero to the unused factors, then save. These numbers are your input, not application defaults. Create a second differently named profile.

Expected: both profiles appear independently. Edit the first profile, choose Remote only, change Skills to 60 and Location/work arrangement to 40, save, reopen, and reload. Its values should persist; the second profile remains unchanged.

Try a weight total other than 100, a positive weight without criteria, overlapping preferred/required skills, an excluded keyword identical to a desired skill, or minimum experience above maximum. Expected: clear validation and no save; entered values remain available to correct. Remote-only plus a location is valid. Delete one profile and verify the other remains.

From `apps/api`:

```powershell
uv run --no-sync pytest -q tests/test_preferences.py
```

Expected: document rules, independent persistence, names, safe errors, isolation, and permission tests pass.

## 4. Sessions, private data, and navigation

Open another browser profile/private window and register a different account. Its company/preference lists should be empty, and copying the first user's edit URL should show not found. Matching entries saved independently under different accounts are allowed.

In the first browser, open an editor, delete only `dev-access` in developer tools, then save a valid change. Expected: the access session refreshes, CSRF is renewed, and the save succeeds. Open another tab and sign out there: protected company/preference pages redirect to login. No auth tokens or form drafts should appear in local/session storage.

## 5. Run automated checks

From `apps/api`:

```powershell
uv sync --locked
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync mypy
uv run --no-sync pytest -q
uv run --no-sync pip-audit --progress-spinner off
```

From `apps/web`, using Node 22.22.3:

```powershell
npm ci
npm run lint
npm test
npm run build
npm audit --audit-level=high
```

Expected: all gates pass. PostgreSQL tests require Docker and use disposable containers. `pytest -m "not integration"` is an explicitly partial, unit-only check. The migration-preservation test upgrades/downgrades only its own test database; never run a downgrade against your saved accounts to reproduce that test.

## 6. Real browser regression in an isolated stack

From root:

```powershell
docker compose --env-file .env -p career-phase2-test -f compose.yaml -f compose.test.yaml up --build -d --wait --wait-timeout 180
```

From `apps/web`:

```powershell
npx playwright install chromium
npm run e2e
```

Expected: eight journeys pass against <http://127.0.0.1:18080>, covering Phase 0/1 regression and the Phase 2 forms, duplicate/conflict errors, persistence, isolation, refresh-on-save, cross-tab logout, and a narrow viewport.

The test database is disposable; retain real local accounts in the normal 8080 development stack. From root, clean up only the test stack:

```powershell
docker compose --env-file .env -p career-phase2-test -f compose.yaml -f compose.test.yaml down --volumes
```

For the regular development stack, `docker compose down` without `--volumes` preserves its database. Phase 2 ends here; there are no scan or matching controls to test yet.
