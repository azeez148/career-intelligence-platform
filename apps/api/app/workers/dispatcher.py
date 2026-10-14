import asyncio
import logging
from datetime import UTC, datetime, timedelta

from celery import Celery  # type: ignore[import-untyped]
from sqlalchemy import and_, or_, select

from app.core.config import Settings
from app.core.logging import configure_logging
from app.db.session import Database
from app.modules.discovery.models import DiscoveryScan, ScanOutbox
from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


async def dispatch_once(database: Database, publisher: Celery, limit: int = 20) -> int:
    now = datetime.now(UTC)
    stale = now - timedelta(seconds=30)
    async with database.sessions() as db, db.begin():
        rows = list(
            (
                await db.scalars(
                    select(ScanOutbox)
                    .join(DiscoveryScan, DiscoveryScan.id == ScanOutbox.scan_id)
                    .where(
                        or_(
                            and_(
                                DiscoveryScan.status == "queued",
                                or_(
                                    DiscoveryScan.next_attempt_at.is_(None),
                                    DiscoveryScan.next_attempt_at <= now,
                                ),
                            ),
                            and_(
                                DiscoveryScan.status == "running",
                                DiscoveryScan.lease_expires_at <= now,
                            ),
                        ),
                        ScanOutbox.available_at <= now,
                        or_(ScanOutbox.dispatched_at.is_(None), ScanOutbox.dispatched_at <= stale),
                    )
                    .order_by(ScanOutbox.available_at, ScanOutbox.scan_id)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        for row in rows:
            try:
                await asyncio.to_thread(
                    publisher.send_task,
                    "discovery.run",
                    args=[str(row.scan_id)],
                    task_id=f"scan:{row.scan_id}",
                )
            except Exception:
                row.publish_attempts += 1
                row.last_error_code = "broker_unavailable"
                row.available_at = now + timedelta(seconds=min(2**row.publish_attempts, 60))
                logger.exception("scan_dispatch_failed")
            else:
                row.dispatched_at = now
                row.last_error_code = None
        return len(rows)


async def run() -> None:
    settings = Settings()
    configure_logging(settings.log_level)
    database = Database(settings)
    try:
        while True:
            count = await dispatch_once(database, celery)
            await asyncio.sleep(0.25 if count else 1)
    finally:
        await database.close()


if __name__ == "__main__":
    asyncio.run(run())
