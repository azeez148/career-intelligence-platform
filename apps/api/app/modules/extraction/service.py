from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError
from app.modules.extraction.models import ExtractionRun
from app.modules.extraction.schemas import ExtractionRunView


def view(run: ExtractionRun) -> ExtractionRunView:
    return ExtractionRunView.model_validate(run, from_attributes=True)


async def owned(db: AsyncSession, user_id: UUID, run_id: UUID) -> ExtractionRun:
    run = await db.scalar(
        select(ExtractionRun).where(ExtractionRun.id == run_id, ExtractionRun.user_id == user_id)
    )
    if run is None:
        raise DomainError(404, "not_found", "Extraction run not found")
    return run
