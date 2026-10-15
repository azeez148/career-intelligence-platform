from uuid import UUID

import httpx
import pytest
from auth_helpers import ORIGIN, mutate, register_login
from sqlalchemy import delete, func, select
from test_matching_api import queued_run, setup

from app.integrations.ai.provider import (
    AIInvalidOutput,
    AIUnavailable,
    Assessment,
    AssessmentOutcome,
    AssessmentRequest,
    DisabledProvider,
    Usage,
)
from app.modules.authorization.models import Permission, RolePermission
from app.modules.matching.models import AIAssessment, AIUsage, JobMatch
from app.workers.matching_tasks import process_match_run

pytestmark = pytest.mark.integration


class FakeProvider:
    name = "fake"
    model = "fake-model"
    prompt_version = "assess-1"
    enabled = True

    def __init__(self, result: AssessmentOutcome | Exception) -> None:
        self.result = result
        self.calls: list[AssessmentRequest] = []

    def cache_key(self) -> tuple[str, str, str]:
        return (self.name, self.model, self.prompt_version)

    async def assess(self, request: AssessmentRequest) -> AssessmentOutcome:
        self.calls.append(request)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


GOOD = AssessmentOutcome(
    Assessment(summary="Mentions Python; seniority not stated.", requirements=["Python"], notes=[]),
    Usage(120, 300, 40, 340),
)


async def test_ai_is_disabled_by_default(api):
    client, app = api
    profile, ids = await setup(api)
    assert isinstance(app.state.ai_provider, DisabledProvider)
    path = f"/preferences/{profile['id']}/matches/{ids['engineer']}/ai-assessment"
    response = await mutate(client, "POST", path)
    assert response.status_code == 403 and response.json()["error"]["code"] == "ai_disabled"
    assert (await client.get("/api/v1/ai/status")).json() == {
        "enabled": False,
        "daily_limit": 20,
        "remaining_today": 0,
    }


async def test_success_is_cached_recorded_and_advisory_only(api):
    client, app = api
    profile, ids = await setup(api)
    fake = FakeProvider(GOOD)
    app.state.ai_provider = fake
    path = f"/preferences/{profile['id']}/matches/{ids['engineer']}/ai-assessment"
    async with app.state.database.sessions() as db:
        before = await db.get(JobMatch, (UUID(profile["id"]), ids["engineer"]))
        assert before is not None
        snapshot = (before.score, before.status, before.explanation)

    first = (await mutate(client, "POST", path)).json()
    assert first["status"] == "succeeded" and first["remaining_today"] == 19
    assert first["assessment"]["result"]["summary"] == "Mentions Python; seniority not stated."
    request = fake.calls[0]
    assert request.title == "Backend Engineer" and "weights" in request.criteria

    second = (await mutate(client, "POST", path)).json()
    assert second["status"] == "cached" and len(fake.calls) == 1
    detail = (
        await client.get(f"/api/v1/preferences/{profile['id']}/matches/{ids['engineer']}")
    ).json()
    assert detail["ai_assessment"]["model"] == "fake-model"

    async with app.state.database.sessions() as db:
        after = await db.get(JobMatch, (UUID(profile["id"]), ids["engineer"]))
        assert after is not None and (after.score, after.status, after.explanation) == snapshot
        usage = (await db.scalars(select(AIUsage))).all()
        assert [(row.status, row.total_tokens, row.latency_ms) for row in usage] == [
            ("succeeded", 340, 120)
        ]

    # Editing preferences changes the criteria hash, so the cached assessment no longer applies.
    edited = {
        "name": "Engineering",
        "criteria": {
            "preferred_skills": ["Python", "Go"],
            "job_titles": ["Backend Engineer"],
            "weights": {
                "skills": 50,
                "title": 50,
                "location": 0,
                "experience": 0,
                "employment": 0,
                "keywords": 0,
            },
        },
    }
    assert (await mutate(client, "PUT", f"/preferences/{profile['id']}", edited)).status_code == 200
    await process_match_run((await queued_run(app, profile["id"])).id, app.state.settings)
    assert (await mutate(client, "POST", path)).json()["status"] == "succeeded"
    assert len(fake.calls) == 2


@pytest.mark.parametrize(
    ("error", "status"),
    [(AIUnavailable(), "unavailable"), (AIInvalidOutput("schema_mismatch"), "invalid_output")],
)
async def test_failures_fall_back_and_are_recorded_but_not_cached(api, error, status):
    client, app = api
    profile, ids = await setup(api)
    app.state.ai_provider = FakeProvider(error)
    path = f"/preferences/{profile['id']}/matches/{ids['engineer']}/ai-assessment"
    response = await mutate(client, "POST", path)
    body = response.json()
    assert response.status_code == 200
    assert (body["status"], body["assessment"]) == (status, None)
    assert "unchanged" in body["message"] or "discarded" in body["message"]
    async with app.state.database.sessions() as db:
        assert await db.scalar(select(func.count()).select_from(AIAssessment)) == 0
        assert [row.status for row in (await db.scalars(select(AIUsage))).all()] == [status]


async def test_daily_cap_ownership_csrf_and_permission(api):
    client, app = api
    profile, ids = await setup(api)
    fake = FakeProvider(AIUnavailable())
    app.state.ai_provider = fake
    app.state.settings.ai_user_daily_limit = 1
    path = f"/preferences/{profile['id']}/matches/{ids['engineer']}/ai-assessment"
    assert (await mutate(client, "POST", path)).json()["remaining_today"] == 0
    limited = await mutate(client, "POST", path)
    assert limited.status_code == 429 and limited.json()["error"]["code"] == "ai_daily_limit"
    assert len(fake.calls) == 1
    app.state.settings.ai_user_daily_limit = 20

    no_csrf = await client.post(f"/api/v1{path}", json={}, headers={"Origin": ORIGIN})
    assert no_csrf.status_code == 403
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as other:
        await register_login(other, "ai-intruder@example.com")
        assert (await mutate(other, "POST", path)).status_code == 404
    assert len(fake.calls) == 1

    async with app.state.database.sessions() as db, db.begin():
        permission = await db.scalar(select(Permission).where(Permission.code == "ai:use:self"))
        assert permission is not None
        await db.execute(
            delete(RolePermission).where(RolePermission.permission_id == permission.id)
        )
    assert (await mutate(client, "POST", path)).status_code == 403
    assert (await client.get("/api/v1/ai/status")).status_code == 403
