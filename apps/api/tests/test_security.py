from datetime import timedelta
from uuid import uuid4

import jwt
import pytest
from fastapi import Request, Response
from pydantic import SecretStr, ValidationError

from app.core.config import Settings
from app.core.errors import DomainError
from app.modules.identity.security import (
    Passwords,
    access_token,
    check_csrf,
    client_address,
    csrf_cookie,
    decode_access,
    now,
    session_cookies,
)


@pytest.fixture
def config():
    return Settings(database_url=SecretStr("postgresql+asyncpg://test:test@localhost/test"))


def request(headers=None, peer="127.0.0.1"):
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "client": (peer, 80),
            "headers": [(key.encode(), value.encode()) for key, value in (headers or {}).items()],
        }
    )


def test_jwt_signature_algorithm_claims_and_expiry(config):
    uid, sid, at = uuid4(), uuid4(), now()
    token = access_token(config, uid, sid, at)
    assert decode_access(config, token) == (uid, sid)
    claims = jwt.decode(token, options={"verify_signature": False})
    for changes in [
        {"exp": int((at - timedelta(seconds=1)).timestamp())},
        {"aud": "other"},
        {"iss": "other"},
        {"sub": "malformed"},
        {"sid": None},
        {"iat": int((at + timedelta(hours=1)).timestamp())},
    ]:
        bad = jwt.encode(
            {**claims, **changes}, config.jwt_secret.get_secret_value(), algorithm="HS256"
        )
        with pytest.raises(DomainError):
            decode_access(config, bad)
    for name in ("sub", "sid", "exp", "iat", "iss", "aud"):
        missing = {key: value for key, value in claims.items() if key != name}
        with pytest.raises(DomainError):
            decode_access(
                config, jwt.encode(missing, config.jwt_secret.get_secret_value(), algorithm="HS256")
            )
    for bad in [
        token + "tampered",
        jwt.encode(claims, "", algorithm="none"),
        jwt.encode(claims, config.jwt_secret.get_secret_value(), algorithm="HS384"),
    ]:
        with pytest.raises(DomainError):
            decode_access(config, bad)


def test_csrf_signed_bound_expiring_and_production_cookies(config):
    at = now()
    response = Response()
    csrf_cookie(response, config, "anonymous", at)
    token = response.headers["set-cookie"].split(";", 1)[0].split("=", 1)[1]
    headers = {
        "origin": "http://testserver",
        "content-type": "application/json",
        "cookie": "XSRF-TOKEN=" + token,
        "x-xsrf-token": token,
    }
    check_csrf(request(headers), config, "anonymous", at)
    for binding, when in [(str(uuid4()), at), ("anonymous", at + timedelta(days=2))]:
        with pytest.raises(DomainError):
            check_csrf(request(headers), config, binding, when)
    for changed in [
        {"origin": "https://evil.example"},
        {"content-type": "text/plain"},
        {"cookie": "XSRF-TOKEN=forged", "x-xsrf-token": "forged"},
    ]:
        with pytest.raises(DomainError):
            check_csrf(request({**headers, **changed}), config, "anonymous", at)
    config = Settings(
        database_url=config.database_url,
        environment="production",
        allowed_origins=["https://career.example"],
    )
    response = Response()
    session_cookies(response, config, uuid4(), uuid4(), "opaque", at + timedelta(days=7), at)
    cookies = response.headers.getlist("set-cookie")
    assert cookies[0].startswith("__Host-access=")
    assert cookies[1].startswith("__Host-refresh=")
    assert all(
        "Secure" in cookie and "Path=/" in cookie and "Domain" not in cookie for cookie in cookies
    )
    assert all("HttpOnly" in cookie for cookie in cookies[:2])


def test_proxy_trust_is_explicit(config):
    headers = {"x-forwarded-for": "203.0.113.1"}
    assert client_address(request(headers), config) == "127.0.0.1"
    config.trusted_proxy_cidrs = ["127.0.0.0/8"]
    assert client_address(request(headers), config) == "203.0.113.1"
    assert client_address(request({"x-forwarded-for": "1.2.3.4, 5.6.7.8"}), config) == "127.0.0.1"


def test_security_configuration_fails_closed(config):
    for overrides in [
        {"jwt_secret": "short"},
        {"csrf_secret": config.jwt_secret},
        {"environment": "production"},
        {"allowed_origins": []},
        {"allowed_origins": ["https://*.example"]},
        {"trusted_proxy_cidrs": ["bad"]},
    ]:
        with pytest.raises(ValidationError):
            Settings(database_url=config.database_url, **overrides)


async def test_password_bounds_dummy_and_worker_capacity():
    passwords = Passwords(1)
    await passwords.initialize()
    password = "  Unicode passphrase 密碼  "
    encoded = await passwords.hash(password)
    assert await passwords.verify(encoded, password)
    assert not await passwords.verify(encoded, password.strip())
    assert not await passwords.verify(None, password)
    await passwords.slots.acquire()
    try:
        with pytest.raises(DomainError) as failure:
            await passwords.hash(password)
        assert failure.value.status == 503
    finally:
        passwords.slots.release()
    assert not passwords.slots.locked()
