import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import text
from testcontainers.community.postgres import PostgresContainer

from app.core.config import Settings
from app.db.session import Database
from app.main import create_app

pytestmark = pytest.mark.integration
API_ROOT = Path(__file__).resolve().parents[1]
POSTGRES_IMAGE = (
    "postgres:17.11-alpine@sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24"
)


@pytest.fixture(scope="module")
def postgres() -> Iterator[PostgresContainer]:
    # Deliberately fail rather than silently skip when Docker is unavailable.
    # Docker may reassign ephemeral ports on restart; pin the chosen free port.
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    with PostgresContainer(POSTGRES_IMAGE, driver="asyncpg").with_bind_ports(
        5432, port
    ) as container:
        yield container


def migrate(url: str, *arguments: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=API_ROOT,
        env={**os.environ, "DATABASE_URL": url},
        check=True,
        timeout=60,
    )


def test_migrations_readiness_and_recovery(postgres: PostgresContainer) -> None:
    url = postgres.get_connection_url()
    settings = Settings(database_url=SecretStr(url), db_ready_timeout=1, db_connect_timeout=0.5)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/health/ready").json()["checks"]["schema"] == "mismatch"
        migrate(url, "upgrade", "head")
        migrate(url, "upgrade", "head")
        assert client.get("/api/v1/health/ready").status_code == 200
        migrate(url, "downgrade", "base")
        assert client.get("/api/v1/health/ready").status_code == 503
        migrate(url, "upgrade", "head")
        assert client.get("/api/v1/health/ready").status_code == 200
        docker_container = postgres.get_wrapped_container()
        docker_container.stop(timeout=1)
        try:
            start = time.monotonic()
            assert client.get("/api/v1/health/ready").status_code == 503
            assert time.monotonic() - start < 3
            assert client.get("/api/v1/health/live").status_code == 200
        finally:
            docker_container.start()
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if client.get("/api/v1/health/ready").status_code == 200:
                break
            time.sleep(0.2)
        else:
            pytest.fail("Readiness did not recover after PostgreSQL restarted")


async def test_sqlalchemy_sessions_and_current_tables(postgres: PostgresContainer) -> None:
    migrate(postgres.get_connection_url(), "upgrade", "head")
    database = Database(Settings(database_url=SecretStr(postgres.get_connection_url())))
    try:
        async with database.sessions() as session:
            assert await session.scalar(text("SELECT 1")) == 1
            tables = await session.scalars(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            )
            assert set(tables) == {
                "alembic_version",
                "users",
                "user_profiles",
                "roles",
                "permissions",
                "user_roles",
                "role_permissions",
                "auth_sessions",
                "refresh_tokens",
                "auth_rate_limits",
                "companies",
                "preference_profiles",
                "discovery_scans",
                "discovery_candidates",
                "career_sources",
                "scan_outbox",
            }
    finally:
        await database.close()
