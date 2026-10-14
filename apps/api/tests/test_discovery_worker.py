import subprocess
import sys
from datetime import UTC, datetime, timedelta
from uuid import UUID

from auth_helpers import mutate, register_login
from sqlalchemy import select

from app.integrations.http import FetchError
from app.integrations.redis import DomainRateLimiter
from app.modules.discovery.models import CareerSource, DiscoveryScan, ScanOutbox
from app.modules.discovery.pipeline import DiscoveredSource, DiscoveryOutcome, DiscoveryPipeline
from app.workers.dispatcher import dispatch_once
from app.workers.tasks import process_scan


async def queued_scan(api, name: str = "Worker Company"):
    client, _ = api
    await register_login(client)
    company = (
        await mutate(
            client,
            "POST",
            "/companies",
            {"name": name, "website_url": f"https://{name.casefold().replace(' ', '')}.com"},
        )
    ).json()
    return (await mutate(client, "POST", f"/companies/{company['id']}/scans")).json()


async def test_worker_persists_success_and_is_idempotent(api, monkeypatch):
    _, app = api
    created = await queued_scan(api)

    async def succeed(self, start_url: str, *, explicit_careers: bool = False):
        return DiscoveryOutcome(
            "succeeded",
            "https://workercompany.com/",
            "user_supplied",
            ["user_supplied_start"],
            [
                DiscoveredSource(
                    "https://jobs.lever.co/workercompany",
                    "ats",
                    "lever",
                    "homepage_link",
                    ["ats_recognized"],
                )
            ],
        )

    monkeypatch.setattr(DiscoveryPipeline, "run", succeed)
    scan_id = UUID(created["id"])
    await process_scan(scan_id, app.state.settings)
    await process_scan(scan_id, app.state.settings)
    async with app.state.database.sessions() as db:
        scan = await db.get(DiscoveryScan, scan_id)
        sources = list(
            (await db.scalars(select(CareerSource).where(CareerSource.scan_id == scan_id))).all()
        )
        assert scan is not None
        assert (scan.status, scan.attempt_count, scan.failure_code) == ("succeeded", 1, None)
        assert [(row.platform, row.url) for row in sources] == [
            ("lever", "https://jobs.lever.co/workercompany")
        ]
        assert await db.get(ScanOutbox, scan_id) is None


async def test_worker_reschedules_transient_failure_then_stops(api, monkeypatch):
    _, app = api
    created = await queued_scan(api, "Retry Company")

    async def fail(self, start_url: str, *, explicit_careers: bool = False):
        raise FetchError("timeout", transient=True)

    monkeypatch.setattr(DiscoveryPipeline, "run", fail)
    scan_id = UUID(created["id"])
    await process_scan(scan_id, app.state.settings)
    async with app.state.database.sessions() as db:
        scan = await db.get(DiscoveryScan, scan_id)
        outbox = await db.get(ScanOutbox, scan_id)
        assert scan is not None and outbox is not None
        assert scan.status == "queued" and scan.failure_code == "timeout"
        assert scan.next_attempt_at is not None and scan.next_attempt_at > datetime.now(UTC)
        assert scan.next_attempt_at <= datetime.now(UTC) + timedelta(seconds=19)
        assert outbox.dispatched_at is None and outbox.available_at == scan.next_attempt_at

    app.state.settings.discovery_max_attempts = 1
    async with app.state.database.sessions() as db, db.begin():
        scan = await db.get(DiscoveryScan, scan_id)
        assert scan is not None
        scan.next_attempt_at = datetime.now(UTC)
    await process_scan(scan_id, app.state.settings)
    async with app.state.database.sessions() as db:
        scan = await db.get(DiscoveryScan, scan_id)
        assert scan is not None and scan.status == "failed" and scan.completed_at is not None
        assert scan.failure_code == "retry_exhausted"
        assert await db.get(ScanOutbox, scan_id) is None


async def test_dispatcher_publishes_due_outbox_once(api):
    _, app = api
    created = await queued_scan(api, "Dispatch Company")
    sent: list[tuple[str, list[str], str]] = []

    class Publisher:
        def send_task(self, name: str, args: list[str], task_id: str):
            sent.append((name, args, task_id))

    assert await dispatch_once(app.state.database, Publisher()) == 1
    assert sent == [("discovery.run", [created["id"]], f"scan:{created['id']}")]
    assert await dispatch_once(app.state.database, Publisher()) == 0

    async with app.state.database.sessions() as db, db.begin():
        scan = await db.get(DiscoveryScan, UUID(created["id"]))
        outbox = await db.get(ScanOutbox, UUID(created["id"]))
        assert scan is not None and outbox is not None
        scan.status = "running"
        scan.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        outbox.dispatched_at = datetime.now(UTC) - timedelta(seconds=31)
    assert await dispatch_once(app.state.database, Publisher()) == 1
    assert len(sent) == 2


def test_worker_process_registers_every_mapped_table():
    code = (
        "import app.workers.tasks, app.workers.dispatcher\n"
        "from app.db.base import Base\n"
        "assert [t.name for t in Base.metadata.sorted_tables]\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


async def test_domain_limiter_waits_for_the_shared_lease(monkeypatch):
    sleeps: list[float] = []

    class Redis:
        attempts = 0

        async def set(self, key: str, value: str, **kwargs):
            self.attempts += 1
            return self.attempts > 1

        async def pttl(self, key: str):
            return 50

    async def sleep(seconds: float):
        sleeps.append(seconds)

    monkeypatch.setattr("app.integrations.redis.anyio.sleep", sleep)
    await DomainRateLimiter(Redis(), 500).acquire("Example.COM")
    assert sleeps == [0.05]
