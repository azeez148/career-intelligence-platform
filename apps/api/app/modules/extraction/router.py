from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.modules.authorization.dependencies import Principal, SessionDependency, require_permission
from app.modules.extraction import service
from app.modules.extraction.schemas import ExtractionRunView
from app.modules.identity.security import check_csrf

router = APIRouter(tags=["extraction"])
Reader = Annotated[Principal, Depends(require_permission("jobs:read:self"))]
Creator = Annotated[Principal, Depends(require_permission("extractions:create:self"))]


@router.get("/extractions/{run_id}", response_model=ExtractionRunView)
async def detail(run_id: UUID, db: SessionDependency, principal: Reader) -> ExtractionRunView:
    return service.view(await service.owned(db, principal.user.id, run_id))


@router.post("/sources/{source_id}/extractions", status_code=202, response_model=ExtractionRunView)
async def start(
    source_id: UUID, request: Request, db: SessionDependency, principal: Creator
) -> ExtractionRunView:
    state = request.app.state
    check_csrf(request, state.settings, str(principal.session.id), state.clock())
    keys: list[str] = []
    try:
        keys.append(
            await state.rate_limits.consume(
                "extraction_user",
                str(principal.user.id),
                state.settings.extraction_user_hour_limit,
                3600,
                state.clock(),
            )
        )
        keys.append(
            await state.rate_limits.consume(
                "extraction_source",
                str(source_id),
                state.settings.extraction_source_hour_limit,
                3600,
                state.clock(),
            )
        )
        result, created = await service.start_manual(db, principal.user.id, source_id)
        if not created:
            for key in keys:
                await state.rate_limits.refund(key)
        return result
    except Exception:
        for key in keys:
            await state.rate_limits.refund(key)
        raise
