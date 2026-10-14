import asyncio
import hashlib
import hmac
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address, ip_network
from typing import TypeVar
from uuid import UUID

import jwt
from argon2 import PasswordHasher, Type
from argon2.exceptions import VerificationError
from fastapi import Request, Response

from app.core.config import Settings
from app.core.errors import DomainError

T = TypeVar("T")


def now() -> datetime:
    return datetime.now(UTC)


def unauthorized() -> DomainError:
    return DomainError(401, "unauthorized", "Authentication required")


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Passwords:
    def __init__(self, workers: int) -> None:
        self.hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=1, type=Type.ID)
        self.slots = asyncio.Semaphore(workers)
        self.dummy = ""

    async def run(self, operation: Callable[[], T]) -> T:
        try:
            async with asyncio.timeout(0.25):
                await self.slots.acquire()
        except TimeoutError:
            raise DomainError(503, "busy", "Please try again shortly") from None
        # Shield the worker: cancellation must not release capacity while Argon2 still runs.
        task = asyncio.create_task(asyncio.to_thread(operation))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise
        finally:
            self.slots.release()

    async def initialize(self) -> None:
        self.dummy = await self.hash(secrets.token_urlsafe(32))

    async def hash(self, password: str) -> str:
        return await self.run(lambda: self.hasher.hash(password))

    async def verify(self, encoded: str | None, password: str) -> bool:
        def operation() -> bool:
            try:
                return self.hasher.verify(encoded or self.dummy, password) and encoded is not None
            except VerificationError:
                return False

        return await self.run(operation)


def access_token(config: Settings, user_id: UUID, session_id: UUID, at: datetime) -> str:
    return jwt.encode(
        {
            "sub": str(user_id),
            "sid": str(session_id),
            "iat": at,
            "exp": at + timedelta(seconds=config.access_token_seconds),
            "iss": config.jwt_issuer,
            "aud": config.jwt_audience,
        },
        config.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )


def decode_access(config: Settings, token: str) -> tuple[UUID, UUID]:
    try:
        claims = jwt.decode(
            token,
            config.jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            issuer=config.jwt_issuer,
            audience=config.jwt_audience,
            options={"require": ["sub", "sid", "iat", "exp", "iss", "aud"]},
        )
        return UUID(claims["sub"]), UUID(claims["sid"])
    except (jwt.InvalidTokenError, ValueError, TypeError, AttributeError):
        raise unauthorized() from None


def csrf_cookie(response: Response, config: Settings, binding: str, at: datetime) -> None:
    payload = f"{binding}.{int(at.timestamp()) + config.csrf_seconds}.{secrets.token_hex(16)}"
    signature = hmac.new(
        config.csrf_secret.get_secret_value().encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    response.set_cookie(
        "XSRF-TOKEN",
        f"{payload}.{signature}",
        max_age=config.csrf_seconds,
        secure=config.secure_cookies,
        httponly=False,
        samesite="lax",
        path="/",
    )


def check_csrf(request: Request, config: Settings, binding: str, at: datetime) -> None:
    denied = DomainError(403, "csrf_failed", "Request verification failed")
    if request.headers.get("origin") not in config.allowed_origins:
        raise denied
    if request.method in {"POST", "PATCH"} and (
        request.headers.get("content-type", "").split(";")[0].lower() != "application/json"
    ):
        raise denied
    token = request.cookies.get("XSRF-TOKEN", "")
    if not token or not hmac.compare_digest(token, request.headers.get("x-xsrf-token", "")):
        raise denied
    try:
        subject, expiry, nonce, signature = token.split(".")
        payload = f"{subject}.{expiry}.{nonce}"
        expected = hmac.new(
            config.csrf_secret.get_secret_value().encode(), payload.encode(), hashlib.sha256
        ).hexdigest()
        if (
            subject != binding
            or int(expiry) <= at.timestamp()
            or not hmac.compare_digest(signature, expected)
        ):
            raise denied
    except (ValueError, OverflowError):
        raise denied from None


def session_cookies(
    response: Response,
    config: Settings,
    user_id: UUID,
    session_id: UUID,
    refresh: str,
    expires: datetime,
    at: datetime,
) -> None:
    response.set_cookie(
        config.access_cookie,
        access_token(config, user_id, session_id, at),
        max_age=config.access_token_seconds,
        httponly=True,
        secure=config.secure_cookies,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        config.refresh_cookie,
        refresh,
        max_age=max(0, int((expires - at).total_seconds())),
        httponly=True,
        secure=config.secure_cookies,
        samesite="lax",
        path="/",
    )
    csrf_cookie(response, config, str(session_id), at)
    response.headers["Cache-Control"] = "no-store"


def clear_cookies(response: Response, config: Settings) -> None:
    for name in (config.access_cookie, config.refresh_cookie, "XSRF-TOKEN"):
        response.delete_cookie(
            name,
            path="/",
            secure=config.secure_cookies,
            httponly=name != "XSRF-TOKEN",
            samesite="lax",
        )


def client_address(request: Request, config: Settings) -> str:
    peer = request.client.host if request.client else "unknown"
    try:
        address = ip_address(peer)
        if any(address in ip_network(network) for network in config.trusted_proxy_cidrs):
            # Only a single overwritten address from the configured edge is accepted.
            return str(ip_address(request.headers.get("x-forwarded-for", peer)))
    except ValueError:
        pass
    return peer
