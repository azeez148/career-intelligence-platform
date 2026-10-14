import asyncio
from uuid import UUID

import httpx
import pytest
from auth_helpers import ORIGIN, mutate, register_login
from sqlalchemy import delete, select

from app.modules.authorization.models import Permission, RolePermission

pytestmark = pytest.mark.integration


async def test_company_crud_and_normalized_duplicates(api):
    client, _ = api
    await register_login(client)
    created = await mutate(client, "POST", "/companies", {"name": "  Example   team  "})
    assert created.status_code == 201
    company = created.json()
    assert company["name"] == "Example team" and company["source_status"] == "unverified"
    assert "user_id" not in company and "identity_key" not in company
    assert created.headers["cache-control"] == "no-store"
    assert (await mutate(client, "POST", "/companies", {"name": "EXAMPLE TEAM"})).status_code == 409
    path = f"/companies/{company['id']}"
    edited = await mutate(
        client,
        "PUT",
        path,
        {
            "website_url": "HTTPS://EXAMPLE.COM:443",
            "careers_url": "https://jobs.example.org/tenant?view=all",
        },
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["name"] is None and edited.json()["display_label"] == "example.com"
    assert (await client.get("/api/v1" + path)).json()[
        "careers_url"
    ] == "https://jobs.example.org/tenant?view=all"
    assert (
        await mutate(client, "POST", "/companies", {"website_url": "https://example.com/"})
    ).status_code == 409
    second = await mutate(
        client, "POST", "/companies", {"careers_url": "https://jobs.example.org/other"}
    )
    assert second.status_code == 201
    page = (await client.get("/api/v1/companies?limit=1")).json()
    assert len(page["items"]) == 1 and page["next_offset"] == 1
    assert len((await client.get("/api/v1/companies?offset=1")).json()["items"]) == 1
    assert (await mutate(client, "DELETE", path)).status_code == 204
    assert (await client.get("/api/v1" + path)).status_code == 404


async def test_company_validation_csrf_and_permissions(api):
    client, app = api
    assert (await client.get("/api/v1/companies")).status_code == 401
    await register_login(client)
    for data in [
        {},
        {"name": " "},
        {"name": "x" * 201},
        {"website_url": "http://127.0.0.1"},
        {"name": "Name", "user_id": str(UUID(int=1))},
        {"name": "Name", "sensitive-unrecognized-field": "secret-value"},
    ]:
        response = await mutate(client, "POST", "/companies", data)
        assert response.status_code == 422
        assert (
            "secret-value" not in response.text
            and "sensitive-unrecognized-field" not in response.text
        )
    assert (await client.post("/api/v1/companies", json={"name": "No csrf"})).status_code == 403
    for query in ("?limit=101", "?offset=-1"):
        assert (await client.get("/api/v1/companies" + query)).status_code == 422
    assert (await client.get("/api/v1/companies/bad-id")).status_code == 422
    async with app.state.database.sessions() as db, db.begin():
        permission = await db.scalar(
            select(Permission.id).where(Permission.code == "companies:create:self")
        )
        await db.execute(delete(RolePermission).where(RolePermission.permission_id == permission))
    assert (await mutate(client, "POST", "/companies", {"name": "Denied"})).status_code == 403


async def test_company_isolation_and_racing_uniqueness(api):
    client, app = api
    await register_login(client)
    cookies = dict(client.cookies)

    async def create():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=ORIGIN, cookies=cookies
        ) as other:
            return await mutate(other, "POST", "/companies", {"name": "Concurrent"})

    results = await asyncio.gather(create(), create())
    assert sorted(row.status_code for row in results) == [201, 409]
    company = next(row.json() for row in results if row.status_code == 201)
    client.cookies.clear()
    await register_login(client, "other@example.com")
    assert (await client.get("/api/v1/companies")).json()["items"] == []
    path = f"/companies/{company['id']}"
    assert (await client.get("/api/v1" + path)).status_code == 404
    assert (await mutate(client, "PUT", path, {"name": "Intruder"})).status_code == 404
    assert (await mutate(client, "DELETE", path)).status_code == 404
    assert (await mutate(client, "POST", "/companies", {"name": "Concurrent"})).status_code == 201


@pytest.mark.parametrize("action", ["read", "create", "update", "delete"])
async def test_each_company_permission_is_enforced_with_existing_session(api, action):
    client, app = api
    await register_login(client)
    created = await mutate(client, "POST", "/companies", {"name": "Owned"})
    path = "/companies/" + created.json()["id"]
    async with app.state.database.sessions() as db, db.begin():
        permission = await db.scalar(
            select(Permission.id).where(Permission.code == f"companies:{action}:self")
        )
        await db.execute(delete(RolePermission).where(RolePermission.permission_id == permission))
    if action == "read":
        assert (await client.get("/api/v1/companies")).status_code == 403
        assert (await client.get("/api/v1" + path)).status_code == 403
    else:
        method, target = {
            "create": ("POST", "/companies"),
            "update": ("PUT", path),
            "delete": ("DELETE", path),
        }[action]
        assert (await mutate(client, method, target, {"name": "Denied"})).status_code == 403


async def test_concurrent_company_updates_have_one_unique_winner(api):
    client, app = api
    await register_login(client)
    ids = [
        (await mutate(client, "POST", "/companies", {"name": name})).json()["id"]
        for name in ("First", "Second")
    ]
    cookies = dict(client.cookies)

    async def update(company_id):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=ORIGIN, cookies=cookies
        ) as other:
            return await mutate(
                other,
                "PUT",
                f"/companies/{company_id}",
                {"website_url": "https://example.com/unique"},
            )

    results = await asyncio.gather(*(update(company_id) for company_id in ids))
    assert sorted(row.status_code for row in results) == [200, 409]
    assert len((await client.get("/api/v1/companies")).json()["items"]) == 2
