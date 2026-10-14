FROM ghcr.io/astral-sh/uv:0.12.24@sha256:3af4716e991d6956a41e573eab705d0ee08500cd829ed30293eb8472f372c65a AS uv
FROM python:3.13.16-alpine3.24@sha256:2d9aefe2fef018a7eb2c13064c89c71929800fd2e5dccdbf52ea5da5bb8d929a AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv/api

FROM base AS dependencies
COPY --from=uv /uv /uvx /bin/
ENV UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-cache

FROM dependencies AS test
RUN uv sync --locked
COPY . .
CMD ["uv", "run", "--no-sync", "pytest", "-m", "not integration", "-q"]

FROM base AS runtime
# Installation tooling is build-only; its vendored packages are unnecessary at runtime.
RUN addgroup -g 10001 app && adduser -D -u 10001 -G app app && python -m pip uninstall --yes pip
COPY --from=dependencies /srv/api/.venv ./.venv
COPY app ./app
COPY alembic.ini ./
COPY migrations ./migrations
USER app:app
EXPOSE 8000
CMD [".venv/bin/uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--no-proxy-headers"]
