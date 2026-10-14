# Phase 4 local checklist

Use a disposable project name so cleanup cannot touch normal development data.

1. **Set the environment.** Export unique `POSTGRES_PASSWORD` and `REDIS_PASSWORD`, three independent 48-byte auth secrets (`JWT_SECRET`, `CSRF_SECRET`, `RATE_LIMIT_SECRET`), `ENVIRONMENT=development`, and `ALLOWED_ORIGINS='["http://127.0.0.1:18080"]'`. Exporting them in your shell, as CI does, avoids writing a `.env` file.
2. **Start the stack.** Run `docker compose -p career-phase4-check -f compose.yaml -f compose.test.yaml up --build -d --wait --wait-timeout 300`. The first build of the browser image takes a few minutes.
3. **Check the services.** Run `docker compose -p career-phase4-check -f compose.yaml -f compose.test.yaml ps`. Expect db, redis, api, web, and fixture-site to be healthy, and worker, browser-worker, and dispatcher to be running.
4. **Check the workers.** Run `docker compose -p career-phase4-check -f compose.yaml -f compose.test.yaml logs worker browser-worker | grep -A4 "\[tasks\]"`. Expect `discovery.run`, `extraction.browser`, and `extraction.run`, and no traceback.
5. **Run a static site end to end.** Register at <http://127.0.0.1:18080>. Add a company with website `http://jobs-fixture.com/` and select **Discover careers**. Within about a minute the scan page shows the `http://jobs-fixture.com/careers` source with "Found 3 jobs." and "3 new · 0 updated · 0 unchanged · 0 no longer listed".
6. **Check job detail.** Select **View jobs from this source** and open **Site Reliability Engineer**. Expect Lisbon, PT; Remote; Full-time; the description and requirements as plain text; and medium confidence. Office Manager shows "Not stated" for the values its page does not state.
7. **Re-extract.** On the scan page, select **Re-extract jobs**. When it finishes, expect "0 new · 0 updated · 3 unchanged · 0 no longer listed".
8. **Run a script-rendered site.** Add a company with website `http://spa-fixture.com/` and discover. Expect the browser stage to run and the panel to show "Rendered page (browser) · low confidence" with 3 jobs.
9. **Check isolation.** In a private window, register a second user. `/jobs` is empty, and opening a job URL from the first user shows "not found".
10. **Run the backend gates.** From `apps/api`:
    - `uv sync --locked --group browser`
    - `uv run --no-sync playwright install --only-shell chromium`
    - `uv run --no-sync ruff check .`
    - `uv run --no-sync ruff format --check .`
    - `uv run --no-sync mypy`
    - `uv run --no-sync pytest -q`
11. **Run the frontend gates.** From `apps/web`, run `npm run lint`, `npm test`, `npm run build`, and `npm run e2e`.
12. **Clean up.** Run `docker compose -p career-phase4-check -f compose.yaml -f compose.test.yaml down --volumes`.

All pipeline, browser-security, and API-strategy tests use in-process fixtures or the local fixture container. None contact a live company or ATS.
