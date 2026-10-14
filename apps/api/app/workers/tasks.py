import asyncio
import logging
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from celery import shared_task  # type: ignore[import-untyped]
from redis.asyncio import Redis
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from app.core.config import Settings
from app.core.logging import configure_logging
from app.db.session import Database
from app.integrations.http import FetchError, SafeHttpClient
from app.integrations.redis import DomainRateLimiter
from app.modules.companies.models import Company
from app.modules.discovery.models import CareerSource, DiscoveryScan, ScanOutbox
from app.modules.discovery.pipeline import DiscoveryOutcome, DiscoveryPipeline

logger = logging.getLogger(__name__)


async def claim(database: Database, scan_id: UUID, settings: Settings) -> tuple[str, bool] | None:
    now = datetime.now(UTC)
    async with database.sessions() as db, db.begin():
        scan = await db.scalar(
            select(DiscoveryScan).where(DiscoveryScan.id == scan_id).with_for_update()
        )
        if scan is None:
            return None
        eligible = scan.status == "queued" and (
            scan.next_attempt_at is None or scan.next_attempt_at <= now
        )
        eligible = eligible or (
            scan.status == "running"
            and scan.lease_expires_at is not None
            and scan.lease_expires_at <= now
        )
        if not eligible or not scan.selected_url:
            return None
        company = await db.get(Company, scan.company_id)
        if company is None:
            return None
        scan.status = "running"
        scan.attempt_count += 1
        scan.started_at = scan.started_at or now
        scan.lease_expires_at = now + timedelta(seconds=settings.discovery_lease_seconds)
        scan.failure_code = None
        return scan.selected_url, company.careers_url == scan.selected_url


async def persist_success(database: Database, scan_id: UUID, outcome: DiscoveryOutcome) -> None:
    now = datetime.now(UTC)
    async with database.sessions() as db, db.begin():
        scan = await db.scalar(
            select(DiscoveryScan).where(DiscoveryScan.id == scan_id).with_for_update()
        )
        if scan is None or scan.status != "running":
            return
        for source in outcome.sources:
            statement = insert(CareerSource).values(
                user_id=scan.user_id,
                company_id=scan.company_id,
                scan_id=scan.id,
                url=source.url,
                kind=source.kind,
                platform=source.platform,
                discovery_method=source.discovery_method,
                evidence=source.evidence,
            )
            await db.execute(
                statement.on_conflict_do_update(
                    constraint="uq_sources_company_url",
                    set_={
                        "scan_id": scan.id,
                        "kind": source.kind,
                        "platform": source.platform,
                        "discovery_method": source.discovery_method,
                        "evidence": source.evidence,
                        "updated_at": now,
                    },
                )
            )
        scan.status = outcome.status
        scan.resolved_website_url = outcome.resolved_website_url
        scan.resolution_confidence = outcome.resolution_confidence
        scan.resolution_evidence = outcome.resolution_evidence
        scan.failure_code = outcome.failure_code
        scan.completed_at = now
        scan.lease_expires_at = None
        await db.execute(delete(ScanOutbox).where(ScanOutbox.scan_id == scan.id))


async def persist_failure(
    database: Database, scan_id: UUID, error: FetchError, settings: Settings
) -> None:
    now = datetime.now(UTC)
    async with database.sessions() as db, db.begin():
        scan = await db.scalar(
            select(DiscoveryScan).where(DiscoveryScan.id == scan_id).with_for_update()
        )
        if scan is None or scan.status != "running":
            return
        retry = error.transient and scan.attempt_count < settings.discovery_max_attempts
        scan.status = "queued" if retry else "failed"
        scan.failure_code = (
            error.code if retry else ("retry_exhausted" if error.transient else error.code)
        )
        scan.lease_expires_at = None
        if retry:
            base = min(15 * (2 ** (scan.attempt_count - 1)), 300)
            delay = error.retry_after or base + secrets.randbelow(max(base // 4, 1) + 1)
            scan.next_attempt_at = now + timedelta(seconds=delay)
            outbox = await db.get(ScanOutbox, scan.id)
            if outbox is None:
                db.add(ScanOutbox(scan_id=scan.id, available_at=scan.next_attempt_at))
            else:
                outbox.available_at = scan.next_attempt_at
                outbox.dispatched_at = None
        else:
            scan.completed_at = now
            await db.execute(delete(ScanOutbox).where(ScanOutbox.scan_id == scan.id))


async def process_scan(scan_id: UUID, settings: Settings | None = None) -> None:
    config = settings or Settings()
    configure_logging(config.log_level)
    database = Database(config)
    redis = Redis.from_url(config.redis_url.get_secret_value(), decode_responses=True)
    try:
        claimed = await claim(database, scan_id, config)
        if claimed is None:
            return
        selected_url, explicit_careers = claimed
        limiter = DomainRateLimiter(redis, config.discovery_domain_interval_ms)
        try:
            async with SafeHttpClient(rate_limit=limiter.acquire) as client:
                outcome = await DiscoveryPipeline(client.fetch).run(
                    selected_url, explicit_careers=explicit_careers
                )
        except FetchError as error:
            await persist_failure(database, scan_id, error, config)
        except Exception:
            logger.exception("discovery_scan_failed", extra={"scan_id": str(scan_id)})
            await persist_failure(
                database, scan_id, FetchError("internal_error", transient=True), config
            )
        else:
            await persist_success(database, scan_id, outcome)
    finally:
        await redis.aclose()
        await database.close()


@shared_task(name="discovery.run")  # type: ignore[untyped-decorator]
def run_discovery(scan_id: str) -> None:
    asyncio.run(process_scan(UUID(scan_id)))
