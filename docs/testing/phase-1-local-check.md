# Check Phase 1 locally, step by step

Run commands from the repository root unless another directory is shown. Keep Docker Desktop running with Linux containers. After each future implementation step, report what changed, how to check it locally, and the expected result.

## 1. Configure and start the application

If `.env` does not exist, copy `.env.example` to `.env`. Choose a unique URL-safe database password and update both `POSTGRES_PASSWORD` and the password in `DATABASE_URL`. Generate each of `JWT_SECRET`, `CSRF_SECRET`, and `RATE_LIMIT_SECRET` separately:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Paste each generated value into its corresponding `.env` entry. Keep `ENVIRONMENT=development` and the example local origins for local HTTP. Never commit `.env`.

```powershell
docker compose up --build -d --wait --wait-timeout 180
docker compose ps
```

Expected: database, API, and web are healthy; the migration service has exited successfully. Open <http://127.0.0.1:8080>. The foundation page reports connected and ready.

## 2. Check the database migration and public health endpoints

```powershell
docker compose exec api .venv/bin/alembic current
docker compose exec api .venv/bin/alembic check
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health/live
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health/ready
```

Expected: revision `0002_identity_profiles_rbac`; no new upgrade operations; live status `ok`; ready status `ready`. Do not test downgrades against your normal database because the downgrade deletes account data.

## 3. Check registration and login

Open **Register**. Enter a display name, a valid email format, and a password of 15–128 characters. Submit, then sign in with those credentials.

Expected: registration redirects to sign-in with confirmation; login opens **Your profile**. A duplicate email produces a clear registration error. A wrong password produces a generic credentials error and clears the password field. Repeated failures are deliberately throttled; use the automated tests for threshold checks rather than locking your manual test account.

## 4. Check profile persistence and input safety

Change **Display name** and **About you**, then select **Save profile**. Reload the page.

Expected: a saved confirmation appears and the new values persist. Empty display names are rejected. Profile text is displayed as text; no HTML execution is supported.

## 5. Check browser session handling

In browser developer tools, inspect cookies and browser storage. Local HTTP uses `dev-access`, `dev-refresh`, and `XSRF-TOKEN`.

Expected: both auth cookies are HttpOnly; local/session storage contains no auth tokens. `XSRF-TOKEN` is intentionally readable for request verification. Production mode uses Secure `__Host-` auth cookies; local development intentionally does not.

Delete **only** `dev-access` and reload the profile. Expected: the session is restored, and the refresh cookie changes. Open a second tab, remove the access cookie again, and reload both tabs together: modern browsers coordinate one refresh. The automated browser suite asserts this explicitly.

## 6. Check session revocation and user isolation

Sign in to the same account in a separate browser profile or private window. In the first browser, open **Sessions**.

Expected: the list shows the current and other sessions. Revoke the other session; its next reload redirects to sign-in. **Sign out everywhere** revokes both sessions. Revoking the current session signs out the current browser.

Register another account in a separate browser profile. Its name/profile/session list must remain separate. Revoking the first account's sessions must not sign out the second account.

## 7. Run backend and authorization tests

From `apps/api`:

```powershell
uv sync --locked
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync mypy
uv run --no-sync pytest -q
uv run --no-sync pip-audit --progress-spinner off
```

Expected for this implementation: **31 tests pass**, including real PostgreSQL permission changes, cross-user access rejection, refresh replay, logout races, rate limits, and migration recovery. Docker is required. For an explicit unit-only check, use `uv run --no-sync pytest -q -m "not integration"`; it does not verify PostgreSQL behavior.

## 8. Run frontend checks

Use Node 22.22.3, then from `apps/web`:

```powershell
npm ci
npm run lint
npm test
npm run build
npm audit --audit-level=high
```

Expected: **15 unit tests pass**, lint/build pass, and no high/critical audit findings. The development machine's older Node 22.22.0 shim is incompatible; select a supported Node installation first. The ignored project-local toolchain, when present, can be invoked with `.tools/node_modules/node/bin/node.exe` and `.tools/node_modules/npm/bin/npm-cli.js` from the repository root.

## 9. Run real browser journeys in an isolated stack

From the repository root, using the `.env` configured in step 1:

```powershell
docker compose --env-file .env -p career-phase1-test -f compose.yaml -f compose.test.yaml up --build -d --wait --wait-timeout 180
```

From `apps/web`:

```powershell
npx playwright install chromium
npm run e2e
```

Expected: **5 browser tests pass** against <http://127.0.0.1:18080>, covering registration, login, profile writes after refresh, concurrent tabs, revocation, user isolation, and foundation health/outage recovery. This stack uses disposable database storage and separate ports; use the normal 8080 stack for accounts you want to retain.

From the repository root, remove only the disposable stack after testing:

```powershell
docker compose --env-file .env -p career-phase1-test -f compose.yaml -f compose.test.yaml down --volumes
```

To stop the normal development stack while retaining its database, use `docker compose down` **without** `--volumes`.

Phase 1 ends here. Phase 2 is not implemented.
