from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from auth_helpers import ORIGIN, mutate, register_login
from sqlalchemy import delete, select

from app.modules.authorization.models import Permission, RolePermission
from app.modules.discovery.models import CareerSource, DiscoveryScan
from app.modules.extraction.models import ExtractionRun
from app.modules.jobs.models import ExtractionRunJob, Job

pytestmark = pytest.mark.integration


def job(user_id: UUID, company_id: UUID, source_id: UUID, title: str, **values) -> Job:
    now = datetime.now(UTC)
    defaults = {
        "dedupe_key": f"test:{title}",
        "canonical_url": f"https://jobs.example/{uuid4()}",
        "work_mode": "unknown",
        "employment_type": "unknown",
        "first_seen_at": now,
        "last_seen_at": now,
        "extraction_method": "ats_api",
        "confidence": "high",
        "field_sources": {"title": "source"},
        "content_hash": "0" * 64,
        "fingerprint": title.casefold(),
    }
    return Job(
        user_id=user_id,
        company_id=company_id,
        source_id=source_id,
        title=title,
        **(defaults | values),
    )


async def seed(app, user_id: UUID, company_id: UUID) -> tuple[UUID, dict[str, UUID]]:
    async with app.state.database.sessions() as db, db.begin():
        scan = DiscoveryScan(
            user_id=user_id,
            company_id=company_id,
            status="succeeded",
            selected_url="https://jobs.example/",
            resolution_evidence=[],
        )
        db.add(scan)
        await db.flush()
        source = CareerSource(
            user_id=user_id,
            company_id=company_id,
            scan_id=scan.id,
            url="https://boards.greenhouse.io/jobsco",
            kind="ats",
            platform="greenhouse",
            discovery_method="homepage_link",
            evidence=["ats_recognized"],
        )
        db.add(source)
        await db.flush()
        older = datetime.now(UTC) - timedelta(days=1)
        rows = {
            "engineer": job(
                user_id,
                company_id,
                source.id,
                "Backend Engineer",
                work_mode="remote",
                employment_type="full_time",
                department="Platform_Team",
                description_text="Build things.\n\n- Python",
            ),
            "designer": job(user_id, company_id, source.id, "Product Designer", last_seen_at=older),
            "closed": job(
                user_id, company_id, source.id, "Closed Role", closed_at=datetime.now(UTC)
            ),
        }
        db.add_all(rows.values())
        await db.flush()
        duplicate = job(
            user_id,
            company_id,
            source.id,
            "Backend Engineer Copy",
            dedupe_key="test:copy",
            confidence="low",
            extraction_method="static_html",
            duplicate_of_job_id=rows["engineer"].id,
        )
        db.add(duplicate)
        run = ExtractionRun(
            user_id=user_id,
            company_id=company_id,
            source_id=source.id,
            scan_id=scan.id,
            trigger="discovery",
            status="succeeded",
            strategy="ats_api",
            confidence="high",
            jobs_found=3,
            complete=True,
        )
        db.add(run)
        await db.flush()
        db.add(ExtractionRunJob(run_id=run.id, job_id=rows["engineer"].id, change="created"))
        ids = {key: row.id for key, row in rows.items()} | {
            "duplicate": duplicate.id,
            "run": run.id,
        }
    return source.id, ids


async def owner(api, email: str) -> tuple[UUID, UUID]:
    client, _ = api
    await register_login(client, email)
    me = (await client.get("/api/v1/users/me")).json()
    company = (
        await mutate(
            client,
            "POST",
            "/companies",
            {"name": f"Co {email}", "website_url": "https://jobs-company.com"},
        )
    ).json()
    return UUID(me["id"]), UUID(company["id"])


async def test_jobs_listing_filters_search_and_detail(api):
    client, app = api
    user_id, company_id = await owner(api, "jobs@example.com")
    source_id, ids = await seed(app, user_id, company_id)

    response = await client.get("/api/v1/jobs")
    assert response.headers["cache-control"] == "no-store"
    page = response.json()
    assert [row["title"] for row in page["items"]] == ["Backend Engineer", "Product Designer"]
    assert page["items"][0]["company_name"] == "Co jobs@example.com"
    assert page["next_offset"] is None

    remote = (await client.get("/api/v1/jobs?work_mode=remote")).json()["items"]
    assert [row["id"] for row in remote] == [str(ids["engineer"])]
    closed = (await client.get("/api/v1/jobs?status=closed")).json()["items"]
    assert [row["id"] for row in closed] == [str(ids["closed"])]
    everything = (await client.get("/api/v1/jobs?status=all&include_duplicates=true")).json()
    assert len(everything["items"]) == 4
    by_source = (await client.get(f"/api/v1/jobs?source_id={source_id}&limit=1")).json()
    assert len(by_source["items"]) == 1 and by_source["next_offset"] == 1

    assert [
        row["id"] for row in (await client.get("/api/v1/jobs?q=platform_")).json()["items"]
    ] == [str(ids["engineer"])]
    # LIKE wildcards in user input are literal, not patterns.
    assert (await client.get("/api/v1/jobs?q=%25")).json()["items"] == []
    assert (await client.get("/api/v1/jobs?q=_")).json()["items"][0]["id"] == str(ids["engineer"])
    assert (await client.get("/api/v1/jobs?q=" + "x" * 101)).status_code == 422
    assert (await client.get("/api/v1/jobs?work_mode=moon")).status_code == 422

    detail = (await client.get(f"/api/v1/jobs/{ids['engineer']}")).json()
    assert detail["description_text"] == "Build things.\n\n- Python"
    assert detail["requirements_text"] is None and detail["valid_through"] is None
    assert detail["field_sources"] == {"title": "source"}
    assert [row["run_id"] for row in detail["observations"]] == [str(ids["run"])]

    run = (await client.get(f"/api/v1/extractions/{ids['run']}")).json()
    assert run["status"] == "succeeded" and run["jobs_found"] == 3 and run["complete"] is True


async def test_jobs_are_owner_scoped_and_permission_gated(api):
    client, app = api
    user_id, company_id = await owner(api, "first@example.com")
    _, ids = await seed(app, user_id, company_id)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as other:
        await register_login(other, "second@example.com")
        assert (await other.get("/api/v1/jobs")).json()["items"] == []
        assert (await other.get(f"/api/v1/jobs/{ids['engineer']}")).status_code == 404
        assert (await other.get(f"/api/v1/extractions/{ids['run']}")).status_code == 404
        assert (await other.get(f"/api/v1/jobs?company_id={company_id}")).json()["items"] == []

    assert (await client.get(f"/api/v1/jobs/{uuid4()}")).status_code == 404
    assert (await client.get("/api/v1/jobs/not-a-uuid")).status_code == 422

    async with app.state.database.sessions() as db, db.begin():
        permission = await db.scalar(select(Permission).where(Permission.code == "jobs:read:self"))
        assert permission is not None
        await db.execute(
            delete(RolePermission).where(RolePermission.permission_id == permission.id)
        )
    assert (await client.get("/api/v1/jobs")).status_code == 403
    assert (await client.get(f"/api/v1/jobs/{ids['engineer']}")).status_code == 403

    anonymous = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN)
    async with anonymous:
        assert (await anonymous.get("/api/v1/jobs")).status_code == 401
