import asyncio
from datetime import timedelta
from uuid import UUID

import httpx
import pytest
from auth_helpers import ORIGIN, PASSWORD, mutate, register_login
from sqlalchemy import delete, select

from app.modules.authorization.models import RolePermission
from app.modules.identity.models import AuthSession, RefreshToken
from app.modules.identity.security import access_token, digest, now
from app.modules.users.models import User

pytestmark = pytest.mark.integration


async def test_registration_validation_duplicates_and_password_protection(api):
    client, app = api
    for data in [
        {"email": "invalid", "password": PASSWORD, "display_name": "Name"},
        {"email": "a@example.com", "password": "short", "display_name": "Name"},
        {"email": "a@example.com", "password": PASSWORD, "display_name": " "},
        {"email": "a@example.com", "password": PASSWORD, "display_name": "Name", "role": "admin"},
    ]:
        response = await mutate(client, "POST", "/auth/register", data)
        assert response.status_code == 422
        assert PASSWORD not in response.text
    result = await register_login(client, "Person@Example.com")
    assert "token" not in result.text and PASSWORD not in result.text
    assert result.json()["user"]["email"] == "person@example.com"
    duplicate = await mutate(
        client,
        "POST",
        "/auth/register",
        {"email": "PERSON@example.com", "password": PASSWORD, "display_name": "Another"},
    )
    assert duplicate.status_code == 409
    async with app.state.database.sessions() as db:
        user = await db.scalar(select(User))
        assert user.password_hash.startswith("$argon2id$v=19$m=65536,t=3,p=1$")
        assert PASSWORD not in user.password_hash
        token = await db.scalar(select(RefreshToken))
        assert token.digest == digest(client.cookies["dev-refresh"])
        assert token.digest != client.cookies["dev-refresh"]
    assert "HttpOnly" in result.headers.get_list("set-cookie")[0]
    assert result.headers["cache-control"] == "no-store"


async def test_login_csrf_limits_and_immediate_logout(api):
    client, app = api
    assert (await client.get("/api/v1/users/me")).status_code == 401
    response = await client.post(
        "/api/v1/auth/login", json={"email": "a@example.com", "password": PASSWORD}
    )
    assert response.status_code == 403
    await register_login(client)
    original = dict(client.cookies)
    for email in ("person@example.com", "missing@example.com"):
        response = await mutate(
            client, "POST", "/auth/login", {"email": email, "password": PASSWORD + "wrong"}
        )
        assert response.status_code == 401
        assert response.json()["error"]["message"] == "Email or password is incorrect"
    for _ in range(4):
        assert (
            await mutate(
                client,
                "POST",
                "/auth/login",
                {"email": "person@example.com", "password": PASSWORD + "wrong"},
            )
        ).status_code == 401
    limited = await mutate(
        client, "POST", "/auth/login", {"email": "person@example.com", "password": PASSWORD}
    )
    assert limited.status_code == 429 and int(limited.headers["retry-after"]) > 0
    assert (await mutate(client, "POST", "/auth/logout")).status_code == 204
    client.cookies.update(original)
    assert (await client.get("/api/v1/users/me")).status_code == 401
    assert (await mutate(client, "POST", "/auth/refresh")).status_code == 401


async def test_rotation_replay_and_expired_invalid_jwt(api):
    client, app = api
    result = await register_login(client)
    original = dict(client.cookies)
    sid = (await client.get("/api/v1/auth/sessions")).json()["items"][0]["id"]
    uid = result.json()["user"]["id"]
    client.cookies.set(
        "dev-access",
        access_token(app.state.settings, UUID(uid), UUID(sid), now() - timedelta(hours=1)),
        domain="testserver.local",
        path="/",
    )
    assert (await client.get("/api/v1/users/me")).status_code == 401
    response = await mutate(client, "POST", "/auth/refresh")
    assert response.status_code == 200
    assert client.cookies["dev-refresh"] != original["dev-refresh"]
    assert (await client.get("/api/v1/users/me")).status_code == 200
    newest = dict(client.cookies)
    client.cookies.clear()
    client.cookies.update(original)
    replay = await mutate(client, "POST", "/auth/refresh")
    assert replay.status_code == 401 and "set-cookie" not in replay.headers
    client.cookies.clear()
    client.cookies.update(newest)
    assert (await client.get("/api/v1/users/me")).status_code == 401
    client.cookies.clear()
    client.cookies.set("dev-access", "not.a.jwt")
    assert (await client.get("/api/v1/users/me")).status_code == 401


async def test_permissions_profiles_and_user_isolation(api):
    client, app = api
    first = (await register_login(client)).json()["user"]
    first_session = (await client.get("/api/v1/auth/sessions")).json()["items"][0]["id"]
    assert (
        await mutate(
            client,
            "PATCH",
            "/users/me/profile",
            {"display_name": "Updated", "bio": "Plain text <script>"},
        )
    ).status_code == 200
    assert (
        await mutate(
            client, "PATCH", "/users/me/profile", {"display_name": "Bad", "user_id": first["id"]}
        )
    ).status_code == 422
    client.cookies.clear()
    await register_login(client, "second@example.com")
    assert (await client.get("/api/v1/users/me")).json()["display_name"] == "Person"
    assert (await mutate(client, "DELETE", f"/auth/sessions/{first_session}")).status_code == 404
    async with app.state.database.sessions() as db, db.begin():
        await db.execute(delete(RolePermission).where(RolePermission.permission_id == UUID(int=3)))
    assert (
        await mutate(client, "PATCH", "/users/me/profile", {"display_name": "Denied"})
    ).status_code == 403
    assert (await client.get("/api/v1/users/me")).status_code == 200


async def test_concurrent_refresh_revokes_family_and_logout_cannot_resurrect(api):
    client, app = api
    await register_login(client)
    cookies = dict(client.cookies)

    async def send(path):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=ORIGIN, cookies=cookies
        ) as other:
            return await mutate(other, "POST", path)

    results = await asyncio.gather(send("/auth/refresh"), send("/auth/refresh"))
    assert sorted(result.status_code for result in results) == [200, 401]
    assert (await client.get("/api/v1/users/me")).status_code == 401
    client.cookies.clear()
    await register_login(client, "race@example.com")
    cookies = dict(client.cookies)
    results = await asyncio.gather(send("/auth/refresh"), send("/auth/logout"))
    assert results[1].status_code == 204
    assert results[0].status_code in (200, 401)
    async with app.state.database.sessions() as db:
        assert all(row.revoked_at for row in (await db.scalars(select(AuthSession))).all())


async def test_csrf_origin_binding_and_logout_all(api):
    client, app = api
    await register_login(client)
    for headers in [
        {"Origin": "https://evil.example"},
        {"Origin": ORIGIN},
        {"Origin": ORIGIN, "X-XSRF-TOKEN": "forged"},
    ]:
        assert (
            await client.post("/api/v1/auth/refresh", json={}, headers=headers)
        ).status_code == 403
    assert (await mutate(client, "POST", "/auth/logout-all")).status_code == 204
    assert (await client.get("/api/v1/users/me")).status_code == 401


async def test_duplicate_race_disabled_user_absolute_expiry_and_pagination(api):
    client, app = api
    await client.get("/api/v1/auth/csrf")
    cookies = dict(client.cookies)
    data = {"email": "race@example.com", "password": PASSWORD, "display_name": "Name"}

    async def register():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=ORIGIN, cookies=cookies
        ) as other:
            return await mutate(other, "POST", "/auth/register", data)

    results = await asyncio.gather(register(), register())
    assert sorted(result.status_code for result in results) == [201, 409]
    for _ in range(2):
        assert (
            await mutate(
                client, "POST", "/auth/login", {"email": data["email"], "password": PASSWORD}
            )
        ).status_code == 200
    page = (await client.get("/api/v1/auth/sessions?limit=1")).json()
    assert len(page["items"]) == 1 and page["next_offset"] == 1
    assert len((await client.get("/api/v1/auth/sessions?offset=1")).json()["items"]) == 1
    async with app.state.database.sessions() as db, db.begin():
        user = await db.scalar(select(User))
        user.active = False
    assert (await client.get("/api/v1/users/me")).status_code == 401
    assert (await mutate(client, "POST", "/auth/refresh")).status_code == 401
    async with app.state.database.sessions() as db, db.begin():
        user = await db.scalar(select(User))
        user.active = True
    assert (
        await mutate(client, "POST", "/auth/login", {"email": data["email"], "password": PASSWORD})
    ).status_code == 200
    app.state.clock = lambda: now() + timedelta(days=8)
    assert (await client.get("/api/v1/users/me")).status_code == 401
    # Bootstrap a fresh CSRF token to isolate absolute session expiry from CSRF expiry.
    await client.get("/api/v1/auth/csrf")
    assert (await mutate(client, "POST", "/auth/refresh")).status_code == 401


async def test_rate_limits_atomic_reset_cleanup_and_refund(api):
    from app.core.errors import DomainError
    from app.modules.identity.models import AuthRateLimit

    _, app = api
    limiter = app.state.rate_limits
    at = now().replace(minute=0, second=0, microsecond=0)
    results = await asyncio.gather(
        *[limiter.consume("test", "private@example.com", 3, 60, at) for _ in range(8)],
        return_exceptions=True,
    )
    assert sum(isinstance(result, str) for result in results) == 3
    assert sum(isinstance(result, DomainError) and result.status == 429 for result in results) == 5
    key = next(result for result in results if isinstance(result, str))
    await limiter.refund(key)
    assert await limiter.consume("test", "private@example.com", 3, 60, at) == key
    assert (
        await limiter.consume("test", "private@example.com", 3, 60, at + timedelta(seconds=60))
        != key
    )
    await limiter.consume("test", "private@example.com", 3, 60, at + timedelta(minutes=5))
    async with app.state.database.sessions() as db:
        rows = (await db.scalars(select(AuthRateLimit))).all()
        assert len(rows) == 1
        assert all("private" not in row.key for row in rows)


async def test_password_salt_rehash_and_owned_session_revocation(api):
    from argon2 import PasswordHasher

    client, app = api
    await register_login(client)
    first_cookies = dict(client.cookies)
    async with app.state.database.sessions() as db, db.begin():
        user = await db.scalar(select(User))
        first_hash = user.password_hash
        user.password_hash = PasswordHasher(time_cost=1, memory_cost=8192).hash(PASSWORD)
    assert (
        await mutate(
            client, "POST", "/auth/login", {"email": "person@example.com", "password": PASSWORD}
        )
    ).status_code == 200
    async with app.state.database.sessions() as db:
        user = await db.scalar(select(User))
        assert not app.state.passwords.hasher.check_needs_rehash(user.password_hash)
        assert user.password_hash != first_hash
    sessions = (await client.get("/api/v1/auth/sessions")).json()["items"]
    other = next(row for row in sessions if not row["current"])
    assert (await mutate(client, "DELETE", f"/auth/sessions/{other['id']}")).status_code == 204
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=ORIGIN, cookies=first_cookies
    ) as first:
        assert (await first.get("/api/v1/users/me")).status_code == 401
    assert (await client.get("/api/v1/users/me")).status_code == 200
    current = next(row for row in sessions if row["current"])
    assert (await mutate(client, "DELETE", f"/auth/sessions/{current['id']}")).status_code == 204
    assert "dev-access" not in client.cookies


async def test_logout_revokes_access_session_when_refresh_cookie_is_missing(api):
    client, _ = api
    await register_login(client)
    original = dict(client.cookies)
    del client.cookies["dev-refresh"]
    await client.get("/api/v1/auth/csrf")
    assert (await mutate(client, "POST", "/auth/logout")).status_code == 204
    client.cookies.clear()
    client.cookies.update(original)
    assert (await client.get("/api/v1/users/me")).status_code == 401
    assert (await mutate(client, "POST", "/auth/refresh")).status_code == 401
