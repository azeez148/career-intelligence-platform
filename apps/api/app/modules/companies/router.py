from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.modules.authorization.dependencies import Principal, SessionDependency, require_permission
from app.modules.companies import service
from app.modules.companies.schemas import CompanyInput, CompanyPage, CompanyView
from app.modules.identity.security import check_csrf

router = APIRouter(prefix="/companies", tags=["companies"])
Reader = Annotated[Principal, Depends(require_permission("companies:read:self"))]
Creator = Annotated[Principal, Depends(require_permission("companies:create:self"))]
Editor = Annotated[Principal, Depends(require_permission("companies:update:self"))]
Deleter = Annotated[Principal, Depends(require_permission("companies:delete:self"))]


@router.get("", response_model=CompanyPage)
async def listing(
    db: SessionDependency,
    principal: Reader,
    offset: Annotated[int, Query(ge=0, le=100000)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> CompanyPage:
    return await service.listing(db, principal.user.id, offset, limit)


@router.get("/{company_id}", response_model=CompanyView)
async def detail(company_id: UUID, db: SessionDependency, principal: Reader) -> CompanyView:
    return service.view(await service.owned(db, principal.user.id, company_id))


@router.post("", status_code=201, response_model=CompanyView)
async def create(
    data: CompanyInput, request: Request, db: SessionDependency, principal: Creator
) -> CompanyView:
    check_csrf(
        request, request.app.state.settings, str(principal.session.id), request.app.state.clock()
    )
    return await service.save(db, principal.user.id, data)


@router.put("/{company_id}", response_model=CompanyView)
async def update(
    company_id: UUID, data: CompanyInput, request: Request, db: SessionDependency, principal: Editor
) -> CompanyView:
    check_csrf(
        request, request.app.state.settings, str(principal.session.id), request.app.state.clock()
    )
    return await service.save(db, principal.user.id, data, company_id)


@router.delete("/{company_id}", status_code=204)
async def remove(
    company_id: UUID, request: Request, db: SessionDependency, principal: Deleter
) -> None:
    check_csrf(
        request, request.app.state.settings, str(principal.session.id), request.app.state.clock()
    )
    await service.remove(db, principal.user.id, company_id)
