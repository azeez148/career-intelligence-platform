import os
import secrets
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import Settings
from app.main import create_app

for key in ("JWT_SECRET", "CSRF_SECRET", "RATE_LIMIT_SECRET"):
    os.environ[key] = secrets.token_urlsafe(48)
os.environ["ENVIRONMENT"] = "development"
os.environ["ALLOWED_ORIGINS"] = '["http://testserver"]'


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
