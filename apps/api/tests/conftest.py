import os
import secrets
from collections.abc import Iterator
from uuid import UUID

import httpx
import pytest
from auth_helpers import ORIGIN
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import text
from test_postgres import POSTGRES_IMAGE, migrate
from testcontainers.community.postgres import PostgresContainer

from app.core.config import Settings
from app.main import create_app

for key in ("JWT_SECRET", "CSRF_SECRET", "RATE_LIMIT_SECRET"):
    os.environ[key] = secrets.token_urlsafe(48)
os.environ["ENVIRONMENT"] = "development"
os.environ["ALLOWED_ORIGINS"] = '["http://testserver"]'
os.environ["REDIS_URL"] = "redis://:test-redis-password@127.0.0.1:6379/15"


@pytest.fixture
def client() -> Iterator[TestClient]:
    settings = Settings(
        database_url=SecretStr("postgresql+asyncpg://test:test@127.0.0.1:1/test"),
        db_connect_timeout=0.1,
        db_ready_timeout=0.2,
        _env_file=None,
    )
    with TestClient(create_app(settings), raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def identity_postgres():
    with PostgresContainer(POSTGRES_IMAGE, driver="asyncpg") as container:
        migrate(container.get_connection_url(), "upgrade", "head")
        yield container


@pytest.fixture
async def api(identity_postgres):
    config = Settings(database_url=SecretStr(identity_postgres.get_connection_url()))
    app = create_app(config)
    async with app.router.lifespan_context(app):
        async with app.state.database.sessions() as db, db.begin():
            await db.execute(text("TRUNCATE users, auth_rate_limits CASCADE"))
            for value in range(2, 6):
                await db.execute(
                    text(
                        "INSERT INTO role_permissions(role_id, permission_id) "
                        "VALUES (:role,:permission) "
                        "ON CONFLICT DO NOTHING"
                    ),
                    {"role": UUID(int=1), "permission": UUID(int=value)},
                )
            for resource in ("companies", "preferences"):
                for action in ("read", "create", "update", "delete"):
                    await db.execute(
                        text(
                            "INSERT INTO role_permissions(role_id, permission_id) "
                            "SELECT :role, id FROM permissions WHERE code = :code "
                            "ON CONFLICT DO NOTHING"
                        ),
                        {"role": UUID(int=1), "code": f"{resource}:{action}:self"},
                    )
            for action in ("read", "create", "update"):
                await db.execute(
                    text(
                        "INSERT INTO role_permissions(role_id, permission_id) "
                        "SELECT :role, id FROM permissions WHERE code = :code "
                        "ON CONFLICT DO NOTHING"
                    ),
                    {"role": UUID(int=1), "code": f"scans:{action}:self"},
                )
            for code in ("jobs:read:self", "extractions:create:self"):
                await db.execute(
                    text(
                        "INSERT INTO role_permissions(role_id, permission_id) "
                        "SELECT :role, id FROM permissions WHERE code = :code "
                        "ON CONFLICT DO NOTHING"
                    ),
                    {"role": UUID(int=1), "code": code},
                )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=ORIGIN
        ) as client:
            yield client, app
