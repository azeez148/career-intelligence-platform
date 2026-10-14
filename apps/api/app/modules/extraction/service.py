from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError
from app.modules.discovery.models import CareerSource
from app.modules.extraction.models import ExtractionOutbox, ExtractionRun
from app.modules.extraction.schemas import ExtractionRunView

ACTIVE = ("queued", "running")


def view(run: ExtractionRun) -> ExtractionRunView:
    return ExtractionRunView.model_validate(run, from_attributes=True)


async def owned(db: AsyncSession, user_id: UUID, run_id: UUID) -> ExtractionRun:
    run = await db.scalar(
        select(ExtractionRun).where(ExtractionRun.id == run_id, ExtractionRun.user_id == user_id)
    )
    if run is None:
        raise DomainError(404, "not_found", "Extraction run not found")
    return run


async def active_run(db: AsyncSession, source_id: UUID) -> ExtractionRun | None:
    run: ExtractionRun | None = await db.scalar(
        select(ExtractionRun).where(
            ExtractionRun.source_id == source_id, ExtractionRun.status.in_(ACTIVE)
        )
    )
    return run


async def enqueue_run(
    db: AsyncSession, source: CareerSource, trigger: str, scan_id: UUID | None = None
) -> tuple[ExtractionRun, bool]:
    """Queue one run and its outbox row in the caller's transaction, or return the active run."""
    active = await active_run(db, source.id)
    if active is not None:
        return active, False
    run = ExtractionRun(
        user_id=source.user_id,
        company_id=source.company_id,
        source_id=source.id,
        scan_id=scan_id,
        trigger=trigger,
        stage="static",
        status="queued",
    )
    db.add(run)
    await db.flush()
    db.add(ExtractionOutbox(run_id=run.id))
    return run, True


async def start_manual(
    db: AsyncSession, user_id: UUID, source_id: UUID
) -> tuple[ExtractionRunView, bool]:
    source = await db.scalar(
        select(CareerSource).where(CareerSource.id == source_id, CareerSource.user_id == user_id)
    )
    if source is None:
        raise DomainError(404, "not_found", "Career source not found")
    try:
        run, created = await enqueue_run(db, source, "manual")
        await db.commit()
        await db.refresh(run)
    except IntegrityError:
        await db.rollback()
        active = await active_run(db, source_id)
        if active is None:
            raise
        return view(active), False
    return view(run), created


async def latest_for_sources(db: AsyncSession, source_ids: list[UUID]) -> list[ExtractionRunView]:
    if not source_ids:
        return []
    rows = (
        await db.scalars(
            select(ExtractionRun)
            .where(ExtractionRun.source_id.in_(source_ids))
            .order_by(ExtractionRun.source_id, ExtractionRun.created_at.desc())
            .distinct(ExtractionRun.source_id)
        )
    ).all()
    return [view(row) for row in rows]
