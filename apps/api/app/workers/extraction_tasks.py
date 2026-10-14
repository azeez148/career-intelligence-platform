import asyncio
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from celery import shared_task  # type: ignore[import-untyped]
from redis.asyncio import Redis
from sqlalchemy import delete, select

from app.core.config import Settings
from app.core.logging import configure_logging
from app.db.session import Database
from app.integrations.http import (
    BROWSER_FETCH_LIMITS,
    EXTRACTION_FETCH_LIMITS,
    Fetched,
    FetchError,
    SafeHttpClient,
)
from app.integrations.redis import DomainRateLimiter
from app.modules.discovery.models import CareerSource
from app.modules.extraction.models import ExtractionOutbox, ExtractionRun
from app.modules.extraction.persist import persist_jobs
from app.modules.extraction.runner import ExtractionOutcome, PageStrategy, extract, unsupported
from app.modules.extraction.strategies import (
    ExtractionContext,
    SourceRef,
    StrategyResult,
    static_html,
)
from app.workers.tasks import retry_delay

logger = logging.getLogger(__name__)


async def browser_strategy(
    source: SourceRef, first: Fetched, ctx: ExtractionContext
) -> StrategyResult:
    # Imported lazily: only the browser-worker image installs Playwright.
    from app.modules.extraction.strategies import browser

    return await browser.extract(source, first, ctx)


PAGE_STRATEGIES: dict[str, PageStrategy] = {
    "static": static_html.extract,
    "browser": browser_strategy,
}


async def claim_run(
    database: Database, run_id: UUID, settings: Settings
) -> tuple[SourceRef, str] | None:
    now = datetime.now(UTC)
    async with database.sessions() as db, db.begin():
        run = await db.scalar(
            select(ExtractionRun).where(ExtractionRun.id == run_id).with_for_update()
        )
        if run is None:
            return None
        eligible = run.status == "queued" and (
            run.next_attempt_at is None or run.next_attempt_at <= now
        )
        eligible = eligible or (
            run.status == "running"
            and run.lease_expires_at is not None
            and run.lease_expires_at <= now
        )
        if not eligible:
            return None
        source = await db.get(CareerSource, run.source_id)
        if source is None:
            return None
        run.status = "running"
        run.attempt_count += 1
        run.started_at = run.started_at or now
        run.lease_expires_at = now + timedelta(seconds=settings.extraction_lease_seconds)
        run.failure_code = None
        return SourceRef(source.url, source.platform), run.stage


async def persist_outcome(
    database: Database, run_id: UUID, outcome: ExtractionOutcome, settings: Settings
) -> None:
    now = datetime.now(UTC)
    async with database.sessions() as db, db.begin():
        run = await db.scalar(
            select(ExtractionRun).where(ExtractionRun.id == run_id).with_for_update()
        )
        if run is None or run.status != "running":
            return
        run.lease_expires_at = None
        if outcome.escalate:
            if settings.extraction_browser_enabled and run.stage == "static":
                run.stage = "browser"
                run.status = "queued"
                run.attempt_count = 0
                run.next_attempt_at = None
                outbox = await db.get(ExtractionOutbox, run.id)
                if outbox is None:
                    db.add(ExtractionOutbox(run_id=run.id, available_at=now))
                else:
                    outbox.available_at = now
                    outbox.dispatched_at = None
                return
            outcome = unsupported("no_jobs_recognized")
        source = await db.get(CareerSource, run.source_id)
        run.status = outcome.status
        run.strategy = outcome.strategy
        run.confidence = outcome.confidence
        run.failure_code = outcome.failure_code
        run.complete = outcome.complete
        run.jobs_found = len(outcome.jobs)
        if outcome.status in {"succeeded", "partial"} and source is not None:
            counts = await persist_jobs(
                db, run, source.platform, outcome.jobs, outcome.complete, now
            )
            run.jobs_created = counts.created
            run.jobs_updated = counts.updated
            run.jobs_unchanged = counts.unchanged
            run.jobs_closed = counts.closed
        run.completed_at = now
        await db.execute(delete(ExtractionOutbox).where(ExtractionOutbox.run_id == run.id))


async def persist_failure(
    database: Database, run_id: UUID, error: FetchError, settings: Settings
) -> None:
    now = datetime.now(UTC)
    async with database.sessions() as db, db.begin():
        run = await db.scalar(
            select(ExtractionRun).where(ExtractionRun.id == run_id).with_for_update()
        )
        if run is None or run.status != "running":
            return
        retry = error.transient and run.attempt_count < settings.extraction_max_attempts
        run.status = "queued" if retry else "failed"
        run.failure_code = (
            error.code if retry else ("retry_exhausted" if error.transient else error.code)
        )
        run.lease_expires_at = None
        if retry:
            run.next_attempt_at = now + timedelta(
                seconds=retry_delay(run.attempt_count, error.retry_after)
            )
            outbox = await db.get(ExtractionOutbox, run.id)
            if outbox is None:
                db.add(ExtractionOutbox(run_id=run.id, available_at=run.next_attempt_at))
            else:
                outbox.available_at = run.next_attempt_at
                outbox.dispatched_at = None
        else:
            run.completed_at = now
            await db.execute(delete(ExtractionOutbox).where(ExtractionOutbox.run_id == run.id))


async def extract_source(
    source: SourceRef, stage: str, ctx: ExtractionContext
) -> ExtractionOutcome:
    return await extract(source, ctx, PAGE_STRATEGIES.get(stage))


async def process_run(run_id: UUID, settings: Settings | None = None) -> None:
    config = settings or Settings()
    configure_logging(config.log_level)
    database = Database(config)
    redis = Redis.from_url(config.redis_url.get_secret_value(), decode_responses=True)
    try:
        claimed = await claim_run(database, run_id, config)
        if claimed is None:
            return
        source, stage = claimed
        limiter = DomainRateLimiter(redis, config.discovery_domain_interval_ms)
        try:
            limits = BROWSER_FETCH_LIMITS if stage == "browser" else EXTRACTION_FETCH_LIMITS
            async with SafeHttpClient(limits=limits, rate_limit=limiter.acquire) as client:
                outcome = await extract_source(source, stage, ExtractionContext(client.fetch))
        except FetchError as error:
            await persist_failure(database, run_id, error, config)
        except Exception:
            logger.exception("extraction_run_failed", extra={"run_id": str(run_id)})
            await persist_failure(
                database, run_id, FetchError("internal_error", transient=True), config
            )
        else:
            try:
                await persist_outcome(database, run_id, outcome, config)
            except Exception:
                logger.exception("extraction_persist_failed", extra={"run_id": str(run_id)})
                await persist_failure(
                    database, run_id, FetchError("internal_error", transient=True), config
                )
    finally:
        await redis.aclose()
        await database.close()


@shared_task(name="extraction.run", soft_time_limit=150, time_limit=160)  # type: ignore[untyped-decorator]
def run_extraction(run_id: str) -> None:
    asyncio.run(process_run(UUID(run_id)))


@shared_task(name="extraction.browser", soft_time_limit=170, time_limit=180)  # type: ignore[untyped-decorator]
def run_browser_extraction(run_id: str) -> None:
    asyncio.run(process_run(UUID(run_id)))
