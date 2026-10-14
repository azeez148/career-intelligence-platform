import asyncio
import json
import logging
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from app.api.health import Checks, check_database, migration_heads
from app.core.config import Settings
from app.core.logging import JsonFormatter


def test_live_does_not_access_database(client: TestClient) -> None:
    with patch("app.api.health.check_database", side_effect=AssertionError("DB accessed")):
        response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert len(response.headers["X-Request-ID"]) == 32


@pytest.mark.parametrize("schema,status", [("ok", 200), ("mismatch", 503)])
def test_ready_contract(client: TestClient, schema: str, status: int) -> None:
    with patch("app.api.health.check_database", new_callable=AsyncMock) as check:
        check.return_value = Checks(database="ok", schema=schema)
        response = client.get("/api/v1/health/ready")
    assert response.status_code == status
    assert response.json()["checks"] == {"database": "ok", "schema": schema}
    assert response.headers["Cache-Control"] == "no-store"


def test_unavailable_database_is_sanitized(client: TestClient) -> None:
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"database": "unavailable", "schema": "unknown"},
    }
    assert "postgresql" not in response.text
    assert client.get("/api/v1/health/live").status_code == 200


async def test_readiness_has_total_deadline() -> None:
    database = AsyncMock()
    database.engine.connect = lambda: asyncio.timeout(10)
    with patch("app.api.health.text", side_effect=AssertionError):
        # A slow connection context must be cancelled, not merely given a query timeout.
        class SlowConnection:
            async def __aenter__(self):
                await asyncio.sleep(10)

            async def __aexit__(self, *args):
                return None

        database.engine.connect = SlowConnection
        async with asyncio.timeout(1):
            result = await check_database(database, {"0001_foundation"}, 0.01)
    assert result.database == "unavailable"


def test_errors_do_not_expose_details(client: TestClient) -> None:
    @client.app.get("/test-error")
    async def fail() -> None:
        raise RuntimeError("secret-password")

    @client.app.get("/test-validation")
    async def validated(number: int) -> dict[str, int]:
        return {"number": number}

    for path, status, code in [
        ("/test-error", 500, "internal_error"),
        ("/missing", 404, "http_error"),
        ("/test-validation?number=secret-password", 422, "validation_error"),
    ]:
        response = client.get(path)
        assert response.status_code == status
        assert response.json()["error"]["code"] == code
        assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]
        assert "secret-password" not in response.text


@pytest.mark.parametrize("url", ["sqlite:///local.db", "postgresql://host/db", "not-a-url"])
def test_invalid_database_settings(url: str) -> None:
    with pytest.raises(ValidationError):
        Settings(database_url=SecretStr(url), _env_file=None)


def test_missing_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_timeouts_are_bounded() -> None:
    with pytest.raises(ValidationError):
        Settings(
            database_url=SecretStr("postgresql+asyncpg://user:secret@host/db"),
            db_ready_timeout=0,
            _env_file=None,
        )


def test_invalid_configuration_does_not_print_credentials() -> None:
    with pytest.raises(ValidationError) as failure:
        Settings(database_url="postgresql://user:private-password@host/db", _env_file=None)
    assert "private-password" not in str(failure.value)


def test_structured_logging_excludes_unapproved_fields() -> None:
    record = logging.LogRecord("app", logging.INFO, "", 0, "request_completed", (), None)
    record.request_id = "abc"
    record.password = "secret"
    record.exc_info = (ValueError, ValueError("secret"), None)
    payload = json.loads(JsonFormatter().format(record))
    assert payload["request_id"] == "abc"
    assert payload["level"] == "INFO"
    assert "secret" not in json.dumps(payload)


def test_one_migration_head() -> None:
    assert migration_heads() == {"0004_career_discovery"}
