import asyncio
from uuid import UUID

import httpx
import pytest
from auth_helpers import ORIGIN, mutate, register_login
from sqlalchemy import delete, select, text

from app.modules.authorization.models import Permission, RolePermission

pytestmark = pytest.mark.integration


async def test_name_only_scan_requires_selection_and_preserves_history(api):
    client, app = api
    await register_login(client)
    company = (await mutate(client, "POST", "/companies", {"name": "Example Team"})).json()
    path = f"/companies/{company['id']}/scans"
    created = await mutate(client, "POST", path)
    assert created.status_code == 202, created.text
    scan = created.json()
    assert scan["status"] == "needs_input" and scan["selected_url"] is None
    assert scan["candidates"][0]["url"] == "https://exampleteam.com/"
    assert scan["sources"] == []
    repeated = await mutate(client, "POST", path)
    assert repeated.status_code == 202 and repeated.json()["id"] == scan["id"]
    selected = await mutate(
        client,
        "POST",
        f"/scans/{scan['id']}/selection",
        {"candidate_id": scan["candidates"][0]["id"]},
    )
    assert selected.status_code == 202, selected.text
    child = selected.json()
    assert child["status"] == "queued" and child["parent_scan_id"] == scan["id"]
    assert child["selected_url"] == "https://exampleteam.com/"
    assert (
        await mutate(
            client,
            "POST",
            f"/scans/{scan['id']}/selection",
            {"candidate_id": scan["candidates"][0]["id"]},
        )
    ).json()["id"] == child["id"]
    assert (await client.get(f"/api/v1/scans/{scan['id']}")).json()["status"] == "superseded"
    listing = (await client.get(f"/api/v1/scans?company_id={company['id']}")).json()
    assert [row["id"] for row in listing["items"]] == [child["id"], scan["id"]]
    async with app.state.database.sessions() as db:
        assert (
            await db.scalar(
                text("SELECT count(*) FROM scan_outbox WHERE scan_id=:id"),
                {"id": UUID(child["id"])},
            )
            == 1
        )


async def test_url_scan_is_queued_once_and_selection_is_strict(api):
    client, _ = api
    await register_login(client)
    company = (
        await mutate(client, "POST", "/companies", {"website_url": "https://example.com/team"})
    ).json()
    path = f"/companies/{company['id']}/scans"
    first, second = await asyncio.gather(mutate(client, "POST", path), mutate(client, "POST", path))
    assert first.status_code == second.status_code == 202
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["selected_url"] == "https://example.com/team"
    scan_id = first.json()["id"]
    assert (
        await mutate(
            client, "POST", f"/scans/{scan_id}/selection", {"website_url": "https://x.com"}
        )
    ).status_code == 409
    for payload in (
        {},
        {"website_url": "http://127.0.0.1"},
        {"candidate_id": str(UUID(int=1)), "website_url": "https://example.org"},
        {"website_url": "https://example.org", "owner_id": str(UUID(int=1))},
    ):
        response = await mutate(client, "POST", f"/scans/{scan_id}/selection", payload)
        assert response.status_code in {409, 422}


async def test_scan_ownership_csrf_query_bounds_and_permissions(api):
    client, app = api
    assert (await client.get("/api/v1/scans")).status_code == 401
    await register_login(client)
    company = (await mutate(client, "POST", "/companies", {"name": "Private"})).json()
    no_csrf = await client.post(f"/api/v1/companies/{company['id']}/scans", json={})
    assert no_csrf.status_code == 403
    scan = (await mutate(client, "POST", f"/companies/{company['id']}/scans")).json()
    for query in ("?limit=101", "?offset=-1", "?status=unknown"):
        assert (await client.get("/api/v1/scans" + query)).status_code == 422
    cookies = dict(client.cookies)
    client.cookies.clear()
    await register_login(client, "other@example.com")
    assert (await client.get(f"/api/v1/scans/{scan['id']}")).status_code == 404
    assert (
        await mutate(
            client,
            "POST",
            f"/scans/{scan['id']}/selection",
            {"website_url": "https://example.org"},
        )
    ).status_code == 404
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=ORIGIN, cookies=cookies
    ) as owner:
        assert (await owner.get(f"/api/v1/scans/{scan['id']}")).status_code == 200


@pytest.mark.parametrize("action", ["read", "create", "update"])
async def test_each_scan_permission_is_enforced(api, action):
    client, app = api
    await register_login(client)
    company = (await mutate(client, "POST", "/companies", {"name": "Permission"})).json()
    scan = (await mutate(client, "POST", f"/companies/{company['id']}/scans")).json()
    async with app.state.database.sessions() as db, db.begin():
        permission = await db.scalar(
            select(Permission.id).where(Permission.code == f"scans:{action}:self")
        )
        await db.execute(delete(RolePermission).where(RolePermission.permission_id == permission))
    if action == "read":
        assert (await client.get("/api/v1/scans")).status_code == 403
        assert (await client.get(f"/api/v1/scans/{scan['id']}")).status_code == 403
    elif action == "create":
        other = (await mutate(client, "POST", "/companies", {"name": "Other"})).json()
        assert (await mutate(client, "POST", f"/companies/{other['id']}/scans")).status_code == 403
    else:
        assert (
            await mutate(
                client,
                "POST",
                f"/scans/{scan['id']}/selection",
                {"website_url": "https://example.org"},
            )
        ).status_code == 403
