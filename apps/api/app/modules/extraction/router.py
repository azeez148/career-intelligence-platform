from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.modules.authorization.dependencies import Principal, SessionDependency, require_permission
from app.modules.extraction import service
from app.modules.extraction.schemas import ExtractionRunView

router = APIRouter(tags=["extraction"])
Reader = Annotated[Principal, Depends(require_permission("jobs:read:self"))]


@router.get("/extractions/{run_id}", response_model=ExtractionRunView)
async def detail(run_id: UUID, db: SessionDependency, principal: Reader) -> ExtractionRunView:
    return service.view(await service.owned(db, principal.user.id, run_id))
