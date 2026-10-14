# Local development

## Prerequisites

- Docker Desktop/Engine running Linux containers. On Windows, `docker desktop start` starts Desktop; `docker info` must show a reachable Linux engine.
- Compose >=2.24.4, including `!override` support for isolated test ports.
- Host development: Python 3.13.16 (3.13.15 also tested), uv 0.12.24, Node 22.22.3, npm 10.9.4 or compatible npm.
- Registry/network access for first installation, images, browser downloads, and vulnerability feeds.

## Configuration

Copy root `.env.example` to `.env`. Generate the required independent JWT/CSRF/rate-limit secrets and configure exact origins as described in [authentication operations](authentication.md). Do not commit `.env` or place secrets in frontend configuration.

| Setting | Meaning |
|---|---|
| `POSTGRES_USER`, `POSTGRES_DB` | Compose database identity; default `career` |
| `POSTGRES_PASSWORD` | Required local database password; use URL-safe characters because Compose constructs a connection URL |
| `DATABASE_URL` | Required backend asyncpg URL; used by host API/Alembic, overridden with internal `db` hostname in Compose |
| `LOG_LEVEL` | DEBUG, INFO, WARNING, or ERROR; default INFO |
| `DB_CONNECT_TIMEOUT` | Connection/pool-acquisition limit in seconds, default 2; >0 and <=30 |
| `DB_READY_TIMEOUT` | Total readiness deadline in seconds, default 3; >0 and <=30 |
| `DB_POOL_SIZE` | Optional backend pool bound, default 5, range 1–20; no overflow |
| `API_PORT`, `WEB_PORT` | Loopback-bound Compose host ports; default 8000/8080 |

Backend settings load `.env` relative to the command's working directory. The root `.env` is automatically read by Compose. For host backend commands use `uv run --env-file ../../.env ...` from `apps/api`, or export the environment variables.

## Container workflow

```sh
docker compose up --build -d --wait --wait-timeout 180
docker compose ps
docker compose logs api migrate
docker compose down
```

Data persists after `down`. Do not add `--volumes` to the development command unless deliberately discarding its database. A changed password in `.env` does not reset credentials in an existing PostgreSQL volume.

PostgreSQL runs as UID/GID 70 using the pinned Alpine 17.11 base. The named volume inherits the image directory ownership; the test tmpfs explicitly sets that ownership. Host bind mounts, if introduced later, must be prepared with compatible ownership. The derived image removes `gosu`, so overriding its user to root is unsupported.

## Host workflow

Start only PostgreSQL with the optional loopback port override:

```sh
docker compose -f compose.yaml -f compose.dev.yaml up -d db --wait
cd apps/api
uv sync --locked
uv run --env-file ../../.env --no-sync alembic upgrade head
uv run --env-file ../../.env --no-sync uvicorn app.main:create_app --factory --reload --no-access-log --no-proxy-headers
```

In another terminal, from `apps/web`, run `npm ci` then `npm start`. Open <http://127.0.0.1:4200>. The dev proxy targets API port 8000.

Use a compatible Node executable rather than the host's older 22.22.0 shim. During this implementation a project-local `.tools/node_modules/node/bin/node.exe` and `.tools/node_modules/npm/bin/npm-cli.js` were used. They are ignored and not required when your normal Node is compatible.

## Migrations and diagnostics

- `uv run --env-file ../../.env --no-sync alembic current` shows the revision.
- `uv run --env-file ../../.env --no-sync alembic upgrade head` applies reviewed migrations.
- Downgrades are tested only on disposable databases in this phase.
- `/api/v1/health/live` returns 200 without using PostgreSQL.
- `/api/v1/health/ready` returns 503 for unavailable PostgreSQL or migration mismatch. It returns no database URLs, SQL, or exception details.
- API JSON logs contain UTC timestamp, level, logger, event, and allowlisted request fields. `X-Request-ID` correlates errors with request completion logs. Raw query strings and headers are not included in application access logs.
- A 503 after database restoration warrants checking credentials, host/port, migration revision, and service logs. Restarting a container with a randomly assigned published port can change that port; the integration fixture pins its test port.

## Security and operational limits

Compose is a local development arrangement. Exposed ports bind to loopback; PostgreSQL is private unless the dev override is used. API and web runtime containers run as non-root users. Phase 1 provides authentication, application permissions, and auth rate limits. Production TLS termination, scan rate limits, and backup automation remain outside this phase.

Stop the isolated test stack after verification using the commands in the testing guide. Never use its cleanup command against the development project.
