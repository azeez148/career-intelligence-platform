from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
import pytest
from auth_helpers import ORIGIN, mutate, register_login
from sqlalchemy import func, select, update

from app.integrations.http import FetchError
from app.modules.discovery.models import CareerSource
from app.modules.discovery.pipeline import DiscoveredSource, DiscoveryOutcome, DiscoveryPipeline
from app.modules.extraction.models import ExtractionOutbox, ExtractionRun
from app.modules.extraction.runner import ExtractionOutcome
from app.modules.jobs.models import ExtractionRunJob, Job
from app.modules.jobs.normalize import NormalizedJob
from app.workers import extraction_tasks
from app.workers.dispatcher import dispatch_once
from app.workers.extraction_tasks import process_run
from app.workers.tasks import process_scan

pytestmark = pytest.mark.integration

SOURCES = [
    DiscoveredSource("https://boards.greenhouse.io/acme", "ats", "greenhouse", "homepage_link", []),
    DiscoveredSource("https://acme-co.com/careers", "generic_page", None, "page_signal", []),
]


def posting(title: str, number: int, confidence: str = "high", **values) -> NormalizedJob:
    return NormalizedJob(
        canonical_url=f"https://boards.greenhouse.io/acme/jobs/{number}",
        title=title,
        extraction_method="ats_api" if confidence == "high" else "static_html",
        confidence=confidence,
        source_job_id=str(number),
        location_text="Remote",
        field_sources={"title": "source"},
        **values,
    )


async def discovered(api, monkeypatch) -> tuple[dict, list[ExtractionRun]]:
    client, app = api
    await register_login(client)
    company = (
        await mutate(
            client, "POST", "/companies", {"name": "Acme Co", "website_url": "https://acme-co.com"}
        )
    ).json()
    scan = (await mutate(client, "POST", f"/companies/{company['id']}/scans")).json()

    async def succeed(self, start_url: str, *, explicit_careers: bool = False):
        return DiscoveryOutcome(
            "succeeded", "https://acme-co.com/", "user_supplied", [], list(SOURCES)
        )

    monkeypatch.setattr(DiscoveryPipeline, "run", succeed)
    await process_scan(UUID(scan["id"]), app.state.settings)
    async with app.state.database.sessions() as db:
        runs = list(
            (await db.scalars(select(ExtractionRun).order_by(ExtractionRun.created_at))).all()
        )
    return scan, runs


def fake_outcomes(monkeypatch, outcomes: dict[str, ExtractionOutcome | Exception]) -> None:
    async def extract_source(source, stage, ctx):
        result = outcomes[source.url]
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(extraction_tasks, "extract_source", extract_source)


async def requeue(app, run_id: UUID) -> UUID:
    async with app.state.database.sessions() as db, db.begin():
        run = await db.get(ExtractionRun, run_id)
        assert run is not None
        source = await db.get(CareerSource, run.source_id)
        assert source is not None
        from app.modules.extraction.service import enqueue_run

        created, _ = await enqueue_run(db, source, "manual")
        return created.id


async def test_discovery_success_queues_one_run_per_source_once(api, monkeypatch):
    client, app = api
    scan, runs = await discovered(api, monkeypatch)
    assert [(run.trigger, run.status, run.stage) for run in runs] == [
        ("discovery", "queued", "static")
    ] * 2
    await process_scan(UUID(scan["id"]), app.state.settings)  # duplicate delivery
    async with app.state.database.sessions() as db:
        assert await db.scalar(select(func.count()).select_from(ExtractionRun)) == 2
        assert await db.scalar(select(func.count()).select_from(ExtractionOutbox)) == 2
    detail = (await client.get(f"/api/v1/scans/{scan['id']}")).json()
    assert sorted(row["status"] for row in detail["extractions"]) == ["queued", "queued"]


async def test_run_lifecycle_creates_updates_and_closes_only_after_complete_runs(api, monkeypatch):
    client, app = api
    _, runs = await discovered(api, monkeypatch)
    ats = runs[0] if runs[0].source_id else runs[1]
    async with app.state.database.sessions() as db:
        source = await db.get(CareerSource, ats.source_id)
        assert source is not None
        ats_url = source.url
        other_url = SOURCES[1].url if ats_url == SOURCES[0].url else SOURCES[0].url

    jobs = [posting("Backend Engineer", 1), posting("Designer", 2)]
    fake_outcomes(
        monkeypatch,
        {
            ats_url: ExtractionOutcome("succeeded", "ats_api", "high", jobs, True),
            other_url: ExtractionOutcome("unsupported", failure_code="no_jobs_recognized"),
        },
    )
    for run in runs:
        await process_run(run.id, app.state.settings)
        await process_run(run.id, app.state.settings)  # duplicate delivery is a no-op
    first = (await client.get(f"/api/v1/extractions/{ats.id}")).json()
    assert (first["status"], first["jobs_found"], first["jobs_created"]) == ("succeeded", 2, 2)
    assert first["attempt_count"] == 1 and first["complete"] is True

    # Same content: unchanged. Edited content: updated.
    second_id = await requeue(app, ats.id)
    jobs = [posting("Backend Engineer", 1), posting("Designer", 2, department="Design")]
    fake_outcomes(
        monkeypatch, {ats_url: ExtractionOutcome("succeeded", "ats_api", "high", jobs, True)}
    )
    await process_run(second_id, app.state.settings)
    second = (await client.get(f"/api/v1/extractions/{second_id}")).json()
    assert (second["jobs_unchanged"], second["jobs_updated"], second["jobs_closed"]) == (1, 1, 0)

    # A partial listing that omits a job must not close it.
    partial_id = await requeue(app, ats.id)
    fake_outcomes(
        monkeypatch,
        {ats_url: ExtractionOutcome("partial", "ats_api", "high", jobs[:1], False)},
    )
    await process_run(partial_id, app.state.settings)
    assert (await client.get("/api/v1/jobs")).json()["items"].__len__() == 2

    # A complete listing that omits it closes it; reappearing later reopens it.
    complete_id = await requeue(app, ats.id)
    fake_outcomes(
        monkeypatch,
        {ats_url: ExtractionOutcome("succeeded", "ats_api", "high", jobs[:1], True)},
    )
    await process_run(complete_id, app.state.settings)
    run = (await client.get(f"/api/v1/extractions/{complete_id}")).json()
    assert run["jobs_closed"] == 1
    open_titles = [row["title"] for row in (await client.get("/api/v1/jobs")).json()["items"]]
    assert open_titles == ["Backend Engineer"]
    closed = (await client.get("/api/v1/jobs?status=closed")).json()["items"]
    assert [row["title"] for row in closed] == ["Designer"]

    reopen_id = await requeue(app, ats.id)
    fake_outcomes(
        monkeypatch, {ats_url: ExtractionOutcome("succeeded", "ats_api", "high", jobs, True)}
    )
    await process_run(reopen_id, app.state.settings)
    assert len((await client.get("/api/v1/jobs")).json()["items"]) == 2
    detail = (await client.get(f"/api/v1/jobs/{closed[0]['id']}")).json()
    assert detail["closed_at"] is None and detail["department"] == "Design"
    # Observed as created, updated, then unchanged on reopen; the partial run skipped it.
    assert [row["change"] for row in detail["observations"]] == ["unchanged", "updated", "created"]
    async with app.state.database.sessions() as db:
        assert await db.scalar(select(func.count()).select_from(Job)) == 2
        assert await db.scalar(select(func.count()).select_from(ExtractionRunJob)) == 8


async def test_transient_failures_retry_then_exhaust(api, monkeypatch):
    _, app = api
    _, runs = await discovered(api, monkeypatch)
    run_id = runs[0].id
    fake_outcomes(
        monkeypatch,
        {source.url: FetchError("api_unavailable", transient=True) for source in SOURCES},
    )
    await process_run(run_id, app.state.settings)
    async with app.state.database.sessions() as db:
        run = await db.get(ExtractionRun, run_id)
        outbox = await db.get(ExtractionOutbox, run_id)
        assert run is not None and outbox is not None
        assert (run.status, run.failure_code, run.attempt_count) == ("queued", "api_unavailable", 1)
        assert run.next_attempt_at is not None and run.next_attempt_at > datetime.now(UTC)
        assert outbox.dispatched_at is None
    app.state.settings.extraction_max_attempts = 2
    async with app.state.database.sessions() as db, db.begin():
        await db.execute(
            update(ExtractionRun)
            .where(ExtractionRun.id == run_id)
            .values(next_attempt_at=datetime.now(UTC))
        )
    await process_run(run_id, app.state.settings)
    async with app.state.database.sessions() as db:
        run = await db.get(ExtractionRun, run_id)
        assert run is not None
        assert (run.status, run.failure_code) == ("failed", "retry_exhausted")
        assert await db.get(ExtractionOutbox, run_id) is None


async def test_permanent_failure_and_escalation(api, monkeypatch):
    _, app = api
    _, runs = await discovered(api, monkeypatch)
    fake_outcomes(
        monkeypatch,
        {source.url: ExtractionOutcome("queued", escalate=True) for source in SOURCES},
    )
    app.state.settings.extraction_browser_enabled = False
    await process_run(runs[0].id, app.state.settings)
    app.state.settings.extraction_browser_enabled = True
    await process_run(runs[1].id, app.state.settings)
    async with app.state.database.sessions() as db:
        disabled = await db.get(ExtractionRun, runs[0].id)
        enabled = await db.get(ExtractionRun, runs[1].id)
        assert disabled is not None and enabled is not None
        assert (disabled.status, disabled.failure_code) == ("unsupported", "no_jobs_recognized")
        assert (enabled.status, enabled.stage, enabled.attempt_count) == ("queued", "browser", 0)
        assert await db.get(ExtractionOutbox, runs[1].id) is not None

    sent: list[tuple[str, list[str], str]] = []

    class Publisher:
        def send_task(self, name: str, args: list[str], task_id: str):
            sent.append((name, args, task_id))

    assert await dispatch_once(app.state.database, Publisher()) == 1
    assert sent == [("extraction.browser", [str(runs[1].id)], f"extraction:{runs[1].id}")]
    app.state.settings.extraction_browser_enabled = False

    fake_outcomes(monkeypatch, {source.url: FetchError("dns_blocked") for source in SOURCES})
    third = await requeue(app, runs[0].id)
    await process_run(third, app.state.settings)
    async with app.state.database.sessions() as db:
        run = await db.get(ExtractionRun, third)
        assert run is not None and (run.status, run.failure_code) == ("failed", "dns_blocked")


async def test_dispatcher_publishes_static_runs_and_recovers_expired_leases(api, monkeypatch):
    _, app = api
    _, runs = await discovered(api, monkeypatch)
    sent: list[tuple[str, list[str], str]] = []

    class Publisher:
        def send_task(self, name: str, args: list[str], task_id: str):
            sent.append((name, args, task_id))

    assert await dispatch_once(app.state.database, Publisher()) == 2
    assert {name for name, _, _ in sent} == {"extraction.run"}
    assert await dispatch_once(app.state.database, Publisher()) == 0
    async with app.state.database.sessions() as db, db.begin():
        run = await db.get(ExtractionRun, runs[0].id)
        outbox = await db.get(ExtractionOutbox, runs[0].id)
        assert run is not None and outbox is not None
        run.status = "running"
        run.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        outbox.dispatched_at = datetime.now(UTC) - timedelta(seconds=31)
    assert await dispatch_once(app.state.database, Publisher()) == 1


async def test_cross_source_duplicates_hide_the_lower_confidence_copy(api, monkeypatch):
    client, app = api
    _, runs = await discovered(api, monkeypatch)
    page_copy = posting("Backend  Engineer", 1, confidence="low")
    page_copy.canonical_url = "https://acme-co.com/careers/backend-engineer"
    page_copy.source_job_id = None
    fake_outcomes(
        monkeypatch,
        {
            SOURCES[0].url: ExtractionOutcome(
                "succeeded", "ats_api", "high", [posting("Backend Engineer", 1)], True
            ),
            SOURCES[1].url: ExtractionOutcome("succeeded", "static_html", "low", [page_copy], True),
        },
    )
    for run in reversed(runs):
        await process_run(run.id, app.state.settings)
    visible = (await client.get("/api/v1/jobs")).json()["items"]
    assert [(row["confidence"], row["duplicate_of_job_id"]) for row in visible] == [("high", None)]
    everything = (await client.get("/api/v1/jobs?include_duplicates=true")).json()["items"]
    duplicate = next(row for row in everything if row["confidence"] == "low")
    assert duplicate["duplicate_of_job_id"] == visible[0]["id"]


async def test_manual_extraction_api_is_owned_idempotent_and_limited(api, monkeypatch):
    client, app = api
    _, runs = await discovered(api, monkeypatch)
    source_id = runs[0].source_id
    path = f"/sources/{source_id}/extractions"
    active = await mutate(client, "POST", path)
    assert active.status_code == 202 and active.json()["id"] == str(runs[0].id)

    async with app.state.database.sessions() as db, db.begin():
        await db.execute(
            update(ExtractionRun).where(ExtractionRun.id == runs[0].id).values(status="succeeded")
        )
    created = await mutate(client, "POST", path)
    assert created.status_code == 202
    assert created.json()["trigger"] == "manual" and created.json()["id"] != str(runs[0].id)

    no_csrf = await client.post(f"/api/v1{path}", json={}, headers={"Origin": ORIGIN})
    assert no_csrf.status_code == 403
    assert (await mutate(client, "POST", "/sources/not-a-uuid/extractions")).status_code == 422

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as other:
        await register_login(other, "intruder@example.com")
        assert (await mutate(other, "POST", path)).status_code == 404

    app.state.settings.extraction_source_hour_limit = 1  # one manual run already counted
    async with app.state.database.sessions() as db, db.begin():
        await db.execute(
            update(ExtractionRun)
            .where(ExtractionRun.source_id == source_id)
            .values(status="succeeded")
        )
    assert (await mutate(client, "POST", path)).status_code == 429
    app.state.settings.extraction_source_hour_limit = 5
