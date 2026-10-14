# Job extraction operations

## Runtime roles

| Role | Image | Queues | Notes |
|---|---|---|---|
| `worker` | `career-api` (Alpine) | `discovery`, `extraction` | Discovery and static extraction. |
| `browser-worker` | `career-browser` (Debian + Chromium headless shell) | `extraction-browser` | Concurrency 1, read-only root, 512 MiB `/tmp` tmpfs, 1.5 GiB memory, 512 processes. |
| `dispatcher` | `career-api` | — | Publishes due rows from `scan_outbox` and `extraction_outbox`. |

PostgreSQL stays authoritative; Redis carries only broker messages and per-host rate leases.

## Configuration

| Setting | Default | Meaning |
|---|---|---|
| `EXTRACTION_BROWSER_ENABLED` | `true` in Compose, `false` in code | Lets the static worker escalate script-rendered pages to the browser queue. With `false`, those runs end `unsupported / no_jobs_recognized`. |
| `EXTRACTION_USER_HOUR_LIMIT` | 20 | Manual re-extractions per user per hour. |
| `EXTRACTION_SOURCE_HOUR_LIMIT` | 5 | Manual re-extractions per source per hour. |
| `EXTRACTION_MAX_ATTEMPTS` | 3 | Attempts per stage before `retry_exhausted`. |
| `EXTRACTION_LEASE_SECONDS` | 240 | Running-run lease; it must exceed the browser task's 180 s hard limit. |
| `OUTBOUND_TEST_HOSTS` | `{}` | Test stacks only; rejected in production. Never set it in `compose.yaml`. |

Built-in budgets:
- **Static runs:** 60 responses, 25 MiB, 10 listing pages, 40 detail pages, 1,000 jobs per source, and 100,000 characters per description. Task limits are 150 s soft and 160 s hard.
- **Browser runs:** 240 responses and 40 MiB per run, at most 80 intercepted requests and 45 s per listing render, and 30 s for each of at most 3 detail renders. Task limits are 170 s soft and 180 s hard.

## Observe and recover

- `docker compose ps` should show `worker`, `browser-worker`, and `dispatcher` running. Their logs should list `extraction.run` and `extraction.browser` under `[tasks]`, with no tracebacks.
- Run status is in `GET /api/v1/extractions/{id}` and on the scan detail page.
  - `partial` means a budget or page limit truncated the listing. Those jobs are kept, but nothing is closed.
  - `unsupported` codes describe source limitations: `source_not_found`, `no_jobs_recognized`, `robots_disallowed`, `malformed_content`, `api_unavailable`.
  - `failed` means a terminal fetch error or retry exhaustion.
- A run stuck in `queued` while the worker logs `received` for the same task ID every 30 seconds is failing before it can claim the run. Read the worker traceback.
- Restarting either worker is safe. Expired leases are republished, and duplicate deliveries exit without changing state.
- After rebuilding only the API image, restart `web`, because Nginx resolves `api` once at startup.

## Browser image maintenance

Rebuild `career-browser` at least weekly, and whenever Debian publishes fixes, to pick up security updates. CI fails on any HIGH/CRITICAL finding that has a fixed version and prints the unfixed remainder for review. Don't add packages to the image unless the headless shell links against them. To add a library, check `ldd` on `chrome-headless-shell` inside the image.

## Data and cleanup

Jobs and runs cascade with their company and source. `docker compose down --volumes` deletes all data and is only for disposable projects.
