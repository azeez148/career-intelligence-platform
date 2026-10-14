from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.modules.authorization.dependencies import Principal, SessionDependency, require_permission
from app.modules.discovery import service
from app.modules.discovery.schemas import ScanPage, ScanSelection, ScanView
from app.modules.identity.security import check_csrf

router = APIRouter(tags=["discovery"])
Reader = Annotated[Principal, Depends(require_permission("scans:read:self"))]
Creator = Annotated[Principal, Depends(require_permission("scans:create:self"))]
Editor = Annotated[Principal, Depends(require_permission("scans:update:self"))]
StatusFilter = Literal[
    "queued", "running", "needs_input", "succeeded", "unsupported", "failed", "superseded"
]


@router.post("/companies/{company_id}/scans", status_code=202, response_model=ScanView)
async def start(
    company_id: UUID, request: Request, db: SessionDependency, principal: Creator
) -> ScanView:
    check_csrf(
        request, request.app.state.settings, str(principal.session.id), request.app.state.clock()
    )
    keys: list[str] = []
    try:
        keys.append(
            await request.app.state.rate_limits.consume(
                "scan_user",
                str(principal.user.id),
                request.app.state.settings.scan_user_hour_limit,
                3600,
                request.app.state.clock(),
            )
        )
        keys.append(
            await request.app.state.rate_limits.consume(
                "scan_company",
                str(company_id),
                request.app.state.settings.scan_company_hour_limit,
                3600,
                request.app.state.clock(),
            )
        )
        result, created = await service.start(db, principal.user.id, company_id)
        if not created:
            for key in keys:
                await request.app.state.rate_limits.refund(key)
        return result
    except Exception:
        for key in keys:
            await request.app.state.rate_limits.refund(key)
        raise


@router.get("/scans", response_model=ScanPage)
async def listing(
    db: SessionDependency,
    principal: Reader,
    company_id: UUID | None = None,
    status: StatusFilter | None = None,
    offset: Annotated[int, Query(ge=0, le=100000)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ScanPage:
    return await service.listing(db, principal.user.id, company_id, status, offset, limit)


@router.get("/scans/{scan_id}", response_model=ScanView)
async def detail(scan_id: UUID, db: SessionDependency, principal: Reader) -> ScanView:
    return await service.view(db, await service.owned(db, principal.user.id, scan_id))


@router.post("/scans/{scan_id}/selection", status_code=202, response_model=ScanView)
async def selection(
    scan_id: UUID,
    data: ScanSelection,
    request: Request,
    db: SessionDependency,
    principal: Editor,
) -> ScanView:
    check_csrf(
        request, request.app.state.settings, str(principal.session.id), request.app.state.clock()
    )
    return await service.select_candidate(
        db, principal.user.id, scan_id, data, request.app.state.clock()
    )
