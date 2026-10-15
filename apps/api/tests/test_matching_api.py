from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
import pytest
from auth_helpers import ORIGIN, mutate, register_login
from sqlalchemy import delete, func, select, update
from test_jobs_api import owner, seed

from app.modules.authorization.models import Permission, RolePermission
from app.modules.extraction.models import ExtractionRun
from app.modules.extraction.runner import ExtractionOutcome
from app.modules.jobs.models import Job
from app.modules.matching.models import JobMatch, MatchingOutbox, MatchRun
from app.modules.matching.queue import enqueue_run
from app.workers import extraction_tasks
from app.workers.matching_tasks import claim, process_match_run

pytestmark = pytest.mark.integration


def profile_payload(**criteria) -> dict:
    weights = criteria.pop("weights", {"skills": 50, "title": 50})
    return {
        "name": criteria.pop("name", "Engineering"),
        "criteria": {
            "preferred_skills": ["Python"],
            "job_titles": ["Backend Engineer"],
            **criteria,
            "weights": {
                "skills": 0,
                "title": 0,
                "location": 0,
                "experience": 0,
                "employment": 0,
                "keywords": 0,
            }
            | weights,
        },
    }


async def queued_run(app, profile_id: str) -> MatchRun:
    async with app.state.database.sessions() as db:
        run = await db.scalar(
            select(MatchRun).where(
                MatchRun.profile_id == UUID(profile_id), MatchRun.status == "queued"
            )
        )
        assert run is not None
        return run


async def setup(api) -> tuple[dict, dict[str, UUID]]:
    client, app = api
    user_id, company_id = await owner(api, "matcher@example.com")
    _, ids = await seed(app, user_id, company_id)
    created = await mutate(client, "POST", "/preferences", profile_payload())
    assert created.status_code == 201, created.text
    profile = created.json()
    await process_match_run((await queued_run(app, profile["id"])).id, app.state.settings)
    return profile, ids


async def test_preference_save_queues_and_worker_scores_open_jobs_once(api):
    client, app = api
    profile, ids = await setup(api)
    path = f"/api/v1/preferences/{profile['id']}"
    page = (await client.get(f"{path}/matches")).json()
    # Closed jobs and hidden cross-source copies are not matched.
    assert [(row["job"]["title"], row["score"]) for row in page["items"]] == [
        ("Backend Engineer", 100),
        ("Product Designer", 0),
    ]
    assert page["items"][0]["coverage"] == 1.0 and page["items"][0]["limited"] is False

    async with app.state.database.sessions() as db:
        run = await db.scalar(select(MatchRun).where(MatchRun.profile_id == UUID(profile["id"])))
        assert run is not None
        assert (run.trigger, run.status, run.jobs_scored) == ("preference_update", "succeeded", 2)
        assert await db.get(MatchingOutbox, run.id) is None
        before = await db.scalar(select(func.max(JobMatch.computed_at)))
    await process_match_run(run.id, app.state.settings)  # duplicate delivery is a no-op
    async with app.state.database.sessions() as db:
        assert await db.scalar(select(func.max(JobMatch.computed_at))) == before

    detail = (await client.get(f"{path}/matches/{ids['engineer']}")).json()
    assert detail["algorithm_version"] == "deterministic-1"
    assert detail["explanation"]["factors"][0]["text"] == (
        "Found 1 of 1 skills in the description: Python."
    )
    assert detail["ai_assessment"] is None
    status = (await client.get(f"{path}/match-status")).json()
    assert (status["active"], status["stale"]) == (False, False)


async def test_preference_edits_rescore_and_filters_apply(api):
    client, app = api
    profile, ids = await setup(api)
    path = f"/api/v1/preferences/{profile['id']}"
    changed = profile_payload(
        required_skills=["Rust"], preferred_skills=["Python"], weights={"skills": 100}
    )
    assert (
        await mutate(client, "PUT", f"/preferences/{profile['id']}", changed)
    ).status_code == 200
    assert (await client.get(f"{path}/match-status")).json()["stale"] is True
    run = await queued_run(app, profile["id"])
    assert run.trigger == "preference_update"
    await process_match_run(run.id, app.state.settings)

    eligible = (await client.get(f"{path}/matches")).json()["items"]
    assert [row["status"] for row in eligible] == []
    excluded = (await client.get(f"{path}/matches?status=excluded")).json()["items"]
    assert [row["job"]["title"] for row in excluded] == ["Backend Engineer"]
    assert excluded[0]["summary"] == "A required skill is not mentioned: Rust."
    unknown = (await client.get(f"{path}/matches?status=insufficient_information")).json()
    assert [row["job"]["title"] for row in unknown["items"]] == ["Product Designer"]
    every = (await client.get(f"{path}/matches?status=all&work_mode=remote")).json()["items"]
    assert [row["job"]["id"] for row in every] == [str(ids["engineer"])]
    assert (await client.get(f"{path}/matches?min_score=101")).status_code == 422


async def test_closed_jobs_are_removed_and_extraction_queues_rescoring(api, monkeypatch):
    client, app = api
    profile, ids = await setup(api)
    async with app.state.database.sessions() as db, db.begin():
        await db.execute(
            update(Job).where(Job.id == ids["engineer"]).values(closed_at=datetime.now(UTC))
        )
        designer = await db.get(Job, ids["designer"])
        assert designer is not None
        run = ExtractionRun(
            user_id=designer.user_id,
            company_id=designer.company_id,
            source_id=designer.source_id,
            trigger="manual",
            status="running",
        )
        db.add(run)
    await extraction_tasks.persist_outcome(
        app.state.database,
        run.id,
        ExtractionOutcome("succeeded", "ats_api", "high", [], False),
        app.state.settings,
    )
    queued = await queued_run(app, profile["id"])
    assert queued.trigger == "jobs_changed"
    await process_match_run(queued.id, app.state.settings)
    async with app.state.database.sessions() as db:
        done = await db.get(MatchRun, queued.id)
        assert done is not None and done.jobs_removed == 1
    titles = [
        row["job"]["title"]
        for row in (
            await client.get(f"/api/v1/preferences/{profile['id']}/matches?status=all")
        ).json()["items"]
    ]
    assert titles == ["Product Designer"]


async def test_runs_coalesce_and_wait_while_another_run_is_active(api):
    _, app = api
    profile, _ = await setup(api)
    profile_id = UUID(profile["id"])
    async with app.state.database.sessions() as db, db.begin():
        user_id = await db.scalar(select(MatchRun.user_id).limit(1))
        assert user_id is not None
        first, created = await enqueue_run(db, user_id, profile_id, "manual")
        again, created_again = await enqueue_run(db, user_id, profile_id, "jobs_changed")
        assert created and not created_again and again.id == first.id
        busy = MatchRun(
            user_id=user_id,
            profile_id=profile_id,
            trigger="manual",
            status="running",
            lease_expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
        db.add(busy)
    assert await claim(app.state.database, first.id) is False
    async with app.state.database.sessions() as db:
        waiting = await db.get(MatchRun, first.id)
        outbox = await db.get(MatchingOutbox, first.id)
        assert waiting is not None and outbox is not None
        assert waiting.status == "queued" and waiting.next_attempt_at is not None
        assert outbox.available_at > datetime.now(UTC)
    async with app.state.database.sessions() as db, db.begin():
        await db.execute(delete(MatchRun).where(MatchRun.id == busy.id))
        await db.execute(
            update(MatchRun).where(MatchRun.id == first.id).values(next_attempt_at=None)
        )
    assert await claim(app.state.database, first.id) is True


async def test_matches_api_is_owned_csrf_protected_limited_and_permission_gated(api):
    client, app = api
    profile, ids = await setup(api)
    path = f"/preferences/{profile['id']}/matches/recalculate"
    first = await mutate(client, "POST", path)
    assert first.status_code == 202 and first.json()["trigger"] == "manual"
    assert (await mutate(client, "POST", path)).json()["id"] == first.json()["id"]
    no_csrf = await client.post(f"/api/v1{path}", json={}, headers={"Origin": ORIGIN})
    assert no_csrf.status_code == 403

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as other:
        await register_login(other, "nosy@example.com")
        base = f"/api/v1/preferences/{profile['id']}"
        assert (await other.get(f"{base}/matches")).status_code == 404
        assert (await other.get(f"{base}/matches/{ids['engineer']}")).status_code == 404
        assert (await other.get(f"{base}/match-status")).status_code == 404
        assert (await mutate(other, "POST", path)).status_code == 404

    app.state.settings.matching_user_hour_limit = 1
    async with app.state.database.sessions() as db, db.begin():
        await db.execute(delete(MatchRun).where(MatchRun.profile_id == UUID(profile["id"])))
    assert (await mutate(client, "POST", path)).status_code == 429
    app.state.settings.matching_user_hour_limit = 30

    async with app.state.database.sessions() as db, db.begin():
        permission = await db.scalar(
            select(Permission).where(Permission.code == "matches:read:self")
        )
        assert permission is not None
        await db.execute(
            delete(RolePermission).where(RolePermission.permission_id == permission.id)
        )
    assert (await client.get(f"/api/v1/preferences/{profile['id']}/matches")).status_code == 403
