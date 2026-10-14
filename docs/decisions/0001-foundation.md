# ADR 0001: Phase 0 engineering foundation

Date: 2026-10-14. Status: accepted through the user's Phase 0 plan approval.

## Context and decisions

The initial repository contained only the master plan. Establish a reproducible modular-monolith foundation without speculative domain modules.

| Concern | Decision | Alternative and rationale |
|---|---|---|
| Backend | Python 3.13, FastAPI, Pydantic v2 | Follow mandated stack; verify with installed dependencies and tests |
| Database | PostgreSQL 17, SQLAlchemy 2 async, asyncpg | SQLite would not prove PostgreSQL behavior; synchronous DB access would violate the selected async foundation |
| Migration | Explicit Alembic command / one-shot service | Startup `create_all` or per-worker migrations hide drift and create races |
| Initial schema | Empty baseline revision, no domain tables | Avoid inventing users/jobs tables before their approved phase |
| Dependencies | uv lockfile and npm lockfile; locked installation | Floating installations can silently change compatibility |
| Angular | Stable 22.2.2, standalone, strict TypeScript/templates, Router, SCSS | Registry metadata and official compatibility table require Node >=22.22.3 on the Node 22 line; installed system Node 22.22.0 is insufficient |
| Frontend testing | CLI unit-test builder with Vitest; Playwright Chromium | Matches the generated stable Angular toolchain; other browser engines can be added when cross-browser requirements arrive |
| HTTP routing | Same-origin relative API path | Avoid build-time API host coupling and unnecessary permissive CORS |
| Health | Dependency-independent liveness, DB/schema-aware readiness | A single health check cannot distinguish process failure from dependency outage |
| Errors/logs | Stable JSON errors, generated request IDs, allowlisted log context | Avoid exposing SQL/credentials, raw validation input, exception messages, or user-controlled request IDs |
| Integration tests | Disposable PostgreSQL 17 Testcontainers | Mocks remain useful for unit contracts but cannot prove migrations or outage recovery |

Node 22.22.3 was installed in ignored `.tools/` for local verification because the host version-manager shims otherwise selected the older runtime. This is a local convenience, not a committed runtime or replacement of the user's system Node installation. CI and container builds select the pinned Node release directly.

Docker Desktop changed randomly published ports after a test container restart. The integration fixture now reserves a free host port and explicitly binds it for the container lifetime. This preserves the database address across outage recovery tests; it does not change production code.

The environment contains a Starlette deprecation notice for its HTTPX-based TestClient. The mandated HTTPX stack remains functional and tests pass; no unrequested HTTPX2 migration or warning suppression is introduced.

## Container security decisions

Initial Debian runtime scans found high/critical OS vulnerabilities. Rather than suppress them, the final API uses Python 3.13.16 on Alpine 3.24 with an immutable image digest. Compatibility was verified by installing locked musllinux wheels, running the 14 backend unit tests inside that image, and running the full Compose migration/readiness/browser path. Host integration tests also run on Python 3.13.15. Build-only uv/cache and pip are absent from the final API runtime.

The web runtime uses Nginx 1.30.5 Alpine, resolved from the current stable release and then pinned by digest. Node and uv build images are also digest-pinned. No `latest` or moving stable tags are used in committed runtime definitions.

The current PostgreSQL 17.11 Alpine base had findings exclusively in `gosu`'s bundled Go standard library. A five-line derived Dockerfile removes that unnecessary privilege-switching executable and starts as the existing postgres UID/GID 70. The inspected upstream entrypoint supports non-root startup and only invokes `gosu` as root. Both fresh tmpfs initialization and initial/repeat named-volume startup were verified. This avoids rebuilding Go tooling or accepting vulnerability suppressions. Testcontainers uses the same pinned upstream PostgreSQL server; Compose additionally verifies the derived non-root image.

Final runtime scans for API, web, and database report zero HIGH/CRITICAL findings, with no ignore list. See the recorded [security summary](../testing/security-summary.json). Findings at lower severities are outside this baseline gate; this is not a production security certification.

## Sources checked during implementation

- [Angular compatibility](https://angular.dev/reference/versions), plus npm registry metadata for Angular 22.2.2.
- [SQLAlchemy asyncio](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html).
- [Alembic asyncio integration](https://alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic).
- [Official Python container tags](https://hub.docker.com/_/python) and [Nginx unprivileged images](https://hub.docker.com/r/nginxinc/nginx-unprivileged/tags), with actual pull digests and runtime versions verified locally.

Exact installed dependencies are recorded in `apps/api/uv.lock` and `apps/web/package-lock.json`; runtime images and tools are explicit in Dockerfiles and CI. Updates require compatibility review and rerunning the gates.

## Consequences and boundaries

Local diagnostics are intentionally unauthenticated and disclose only coarse state. There is no user-controlled external URL fetching or AI processing. JWT, Argon2id, refresh-token rotation, RBAC, SSRF controls, domain throttling, and prompt-injection protection must be implemented with the features that require them. Production TLS, secret stores, backup/restore, deployment topology, and release hardening remain later work.
