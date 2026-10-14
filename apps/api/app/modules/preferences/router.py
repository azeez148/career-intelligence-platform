from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.modules.authorization.dependencies import Principal, SessionDependency, require_permission
from app.modules.identity.security import check_csrf
from app.modules.preferences import service
from app.modules.preferences.schemas import PreferenceInput, PreferencePage, PreferenceView

router = APIRouter(prefix="/preferences", tags=["preferences"])
Reader = Annotated[Principal, Depends(require_permission("preferences:read:self"))]
Creator = Annotated[Principal, Depends(require_permission("preferences:create:self"))]
Editor = Annotated[Principal, Depends(require_permission("preferences:update:self"))]
Deleter = Annotated[Principal, Depends(require_permission("preferences:delete:self"))]


@router.get("", response_model=PreferencePage)
async def listing(
    db: SessionDependency,
    principal: Reader,
    offset: Annotated[int, Query(ge=0, le=100000)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PreferencePage:
    return await service.listing(db, principal.user.id, offset, limit)


@router.get("/{profile_id}", response_model=PreferenceView)
async def detail(profile_id: UUID, db: SessionDependency, principal: Reader) -> PreferenceView:
    return service.view(await service.owned(db, principal.user.id, profile_id))


@router.post("", status_code=201, response_model=PreferenceView)
async def create(
    data: PreferenceInput, request: Request, db: SessionDependency, principal: Creator
) -> PreferenceView:
    check_csrf(
        request, request.app.state.settings, str(principal.session.id), request.app.state.clock()
    )
    return await service.save(db, principal.user.id, data)


@router.put("/{profile_id}", response_model=PreferenceView)
async def update(
    profile_id: UUID,
    data: PreferenceInput,
    request: Request,
    db: SessionDependency,
    principal: Editor,
) -> PreferenceView:
    check_csrf(
        request, request.app.state.settings, str(principal.session.id), request.app.state.clock()
    )
    return await service.save(db, principal.user.id, data, profile_id)


@router.delete("/{profile_id}", status_code=204)
async def remove(
    profile_id: UUID, request: Request, db: SessionDependency, principal: Deleter
) -> None:
    check_csrf(
        request, request.app.state.settings, str(principal.session.id), request.app.state.clock()
    )
    await service.remove(db, principal.user.id, profile_id)
