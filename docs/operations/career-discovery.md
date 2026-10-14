# Career discovery operations

## Runtime roles

`api` creates and reads scans. `dispatcher` publishes due outbox rows. `worker` runs `discovery.run`. `redis` is an authenticated, internal-only Celery broker with AOF and `noeviction`. PostgreSQL remains authoritative.

Required configuration is `REDIS_PASSWORD` for Compose and `REDIS_URL` for a host process. Production validation requires a password in the Redis URL. Discovery defaults are a 500 ms exact-host interval, four attempts, a 120-second database lease, a 70-second soft task limit, and a 75-second hard task limit. HTTP defaults are 12 responses, five redirects per chain, 2 MiB per decoded response, 10 MiB total, a five-second connect timeout, and a ten-second read timeout.

## Observe and recover

Use `docker compose ps` to confirm `db`, `redis`, `api`, `worker`, `dispatcher`, and `web` are running; database, Redis, API, and web should report healthy. `docker compose logs worker dispatcher` should show `discovery.run` registered and no configuration traceback.

If Redis is unavailable, scans remain queued in PostgreSQL. Restore Redis and restart `dispatcher` if necessary. Undispatched rows retry with bounded publish backoff; queued rows with stale dispatch timestamps are republished. A running scan whose lease expires is also republished. Duplicate tasks exit unless the row is queued or its running lease has expired.

If scans stay queued while the worker logs `received` for the same task ID every 30 seconds, the task is failing before it can claim the scan; inspect the worker logs for the exception. After rebuilding only the API image, restart `web` as well, because Nginx resolves the `api` address once at startup.

Safe failure codes are user-visible; raw resolver errors and remote bodies are not. `unsupported` indicates a policy or source limitation. `failed` indicates a terminal fetch error or retry exhaustion. Do not bypass robots rules, address checks, response budgets, or TLS verification to make a site pass.

## Data and cleanup

Normal `docker compose down` retains PostgreSQL and Redis volumes. `docker compose down --volumes` deletes both and is appropriate only for an explicitly disposable project. Deleting a company cascades its Phase 3 scans, candidates, sources, and outbox rows.
