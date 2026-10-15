import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from celery import Celery  # type: ignore[import-untyped]
from sqlalchemy import and_, or_, select

from app.core.config import Settings
from app.core.logging import configure_logging
from app.db.session import Database
from app.modules.discovery.models import DiscoveryScan, ScanOutbox
from app.modules.extraction.models import ExtractionOutbox, ExtractionRun
from app.modules.matching.models import MatchingOutbox, MatchRun
from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OutboxKind:
    """One durable work type: its outbox, the state row it drives, and how to name tasks."""

    outbox: Any
    key: Any
    state: Any
    prefix: str

    def task_name(self, state: Any) -> str:
        if self.prefix == "extraction":
            return "extraction.browser" if state.stage == "browser" else "extraction.run"
        if self.prefix == "match":
            return "matching.run"
        return "discovery.run"


KINDS = (
    OutboxKind(ScanOutbox, ScanOutbox.scan_id, DiscoveryScan, "scan"),
    OutboxKind(ExtractionOutbox, ExtractionOutbox.run_id, ExtractionRun, "extraction"),
    OutboxKind(MatchingOutbox, MatchingOutbox.run_id, MatchRun, "match"),
)


async def dispatch_kind(database: Database, publisher: Celery, kind: OutboxKind, limit: int) -> int:
    now = datetime.now(UTC)
    stale = now - timedelta(seconds=30)
    state = kind.state
    async with database.sessions() as db, db.begin():
        rows = list(
            (
                await db.execute(
                    select(kind.outbox, state)
                    .join(state, state.id == kind.key)
                    .where(
                        or_(
                            and_(
                                state.status == "queued",
                                or_(state.next_attempt_at.is_(None), state.next_attempt_at <= now),
                            ),
                            and_(state.status == "running", state.lease_expires_at <= now),
                        ),
                        kind.outbox.available_at <= now,
                        or_(
                            kind.outbox.dispatched_at.is_(None), kind.outbox.dispatched_at <= stale
                        ),
                    )
                    .order_by(kind.outbox.available_at, kind.key)
                    .limit(limit)
                    .with_for_update(skip_locked=True, of=kind.outbox)
                )
            ).all()
        )
        for row, target in rows:
            try:
                await asyncio.to_thread(
                    publisher.send_task,
                    kind.task_name(target),
                    args=[str(target.id)],
                    task_id=f"{kind.prefix}:{target.id}",
                )
            except Exception:
                row.publish_attempts += 1
                row.last_error_code = "broker_unavailable"
                row.available_at = now + timedelta(seconds=min(2**row.publish_attempts, 60))
                logger.exception("dispatch_failed", extra={"kind": kind.prefix})
            else:
                row.dispatched_at = now
                row.last_error_code = None
        return len(rows)


async def dispatch_once(database: Database, publisher: Celery, limit: int = 20) -> int:
    count = 0
    for kind in KINDS:
        count += await dispatch_kind(database, publisher, kind, limit)
    return count


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
