FROM ghcr.io/astral-sh/uv:0.12.24 AS uv
FROM python:3.13.15-slim-bookworm AS base
COPY --from=uv /uv /uvx /bin/
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy
WORKDIR /srv/api
COPY pyproject.toml uv.lock ./

FROM base AS test
RUN uv sync --locked
COPY . .
CMD ["uv", "run", "--no-sync", "pytest", "-m", "not integration", "-q"]

FROM base AS runtime
RUN uv sync --locked --no-dev && useradd --uid 10001 --create-home app
COPY app ./app
COPY alembic.ini ./
COPY migrations ./migrations
USER 10001
EXPOSE 8000
CMD [".venv/bin/uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
