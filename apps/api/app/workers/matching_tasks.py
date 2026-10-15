import asyncio
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from celery import shared_task  # type: ignore[import-untyped]
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.logging import configure_logging
from app.db.session import Database
from app.modules.matching.models import MatchingOutbox, MatchRun
from app.modules.matching.persist import recompute
from app.modules.preferences.models import PreferenceProfile
from app.workers.tasks import retry_delay

logger = logging.getLogger(__name__)
LEASE_SECONDS = 300
MAX_ATTEMPTS = 3
BUSY_DELAY_SECONDS = 5


async def _reschedule(db: AsyncSession, run: MatchRun, at: datetime) -> None:
    run.next_attempt_at = at
    outbox = await db.get(MatchingOutbox, run.id)
    if outbox is None:
        db.add(MatchingOutbox(run_id=run.id, available_at=at))
    else:
        outbox.available_at = at
        outbox.dispatched_at = None


async def claim(database: Database, run_id: UUID) -> bool:
    now = datetime.now(UTC)
    async with database.sessions() as db, db.begin():
        run = await db.scalar(select(MatchRun).where(MatchRun.id == run_id).with_for_update())
        if run is None:
            return False
        if run.status == "running" and run.lease_expires_at and run.lease_expires_at <= now:
            pass  # Recover a crashed attempt.
        elif run.status != "queued" or (run.next_attempt_at and run.next_attempt_at > now):
            return False
        try:
            async with db.begin_nested():
                run.status = "running"
                run.attempt_count += 1
                run.started_at = run.started_at or now
                run.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
                run.failure_code = None
                await db.flush()
        except IntegrityError:
            # Another run for this profile is still running; try again shortly.
            await db.refresh(run)
            await _reschedule(db, run, now + timedelta(seconds=BUSY_DELAY_SECONDS))
            return False
        return True


async def finish(database: Database, run_id: UUID) -> None:
    now = datetime.now(UTC)
    async with database.sessions() as db, db.begin():
        run = await db.scalar(select(MatchRun).where(MatchRun.id == run_id).with_for_update())
        if run is None or run.status != "running":
            return
        profile = await db.get(PreferenceProfile, run.profile_id)
        if profile is None:
            return
        counts = await recompute(db, profile, now)
        run.jobs_scored = counts.scored
        run.jobs_unchanged = counts.unchanged
        run.jobs_removed = counts.removed
        run.status = "succeeded" if counts.complete else "partial"
        run.completed_at = now
        run.lease_expires_at = None
        await db.execute(delete(MatchingOutbox).where(MatchingOutbox.run_id == run.id))


async def fail(database: Database, run_id: UUID) -> None:
    now = datetime.now(UTC)
    async with database.sessions() as db, db.begin():
        run = await db.scalar(select(MatchRun).where(MatchRun.id == run_id).with_for_update())
        if run is None or run.status != "running":
            return
        run.lease_expires_at = None
        if run.attempt_count < MAX_ATTEMPTS:
            run.status = "queued"
            run.failure_code = "internal_error"
            await _reschedule(
                db, run, now + timedelta(seconds=retry_delay(run.attempt_count, None))
            )
        else:
            run.status = "failed"
            run.failure_code = "retry_exhausted"
            run.completed_at = now
            await db.execute(delete(MatchingOutbox).where(MatchingOutbox.run_id == run.id))


async def process_match_run(run_id: UUID, settings: Settings | None = None) -> None:
    config = settings or Settings()
    configure_logging(config.log_level)
    database = Database(config)
    try:
        if not await claim(database, run_id):
            return
        try:
            await finish(database, run_id)
        except Exception:
            logger.exception("match_run_failed", extra={"run_id": str(run_id)})
            await fail(database, run_id)
    finally:
        await database.close()


@shared_task(name="matching.run", soft_time_limit=110, time_limit=120)  # type: ignore[untyped-decorator]
def run_matching(run_id: str) -> None:
    asyncio.run(process_match_run(UUID(run_id)))
