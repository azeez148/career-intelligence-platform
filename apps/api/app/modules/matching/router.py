from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.modules.authorization.dependencies import Principal, SessionDependency, require_permission
from app.modules.identity.security import check_csrf
from app.modules.jobs.schemas import WorkMode
from app.modules.matching import service
from app.modules.matching.schemas import MatchPage, MatchRunView, MatchStatusView, MatchView

router = APIRouter(prefix="/preferences/{profile_id}", tags=["matching"])
Reader = Annotated[Principal, Depends(require_permission("matches:read:self"))]
Updater = Annotated[Principal, Depends(require_permission("matches:update:self"))]


def ai_cache_key(request: Request) -> tuple[str, str, str] | None:
    provider = getattr(request.app.state, "ai_provider", None)
    return provider.cache_key() if provider is not None and provider.enabled else None


@router.get("/matches", response_model=MatchPage)
async def listing(
    profile_id: UUID,
    db: SessionDependency,
    principal: Reader,
    status: Literal["eligible", "excluded", "insufficient_information", "all"] = "eligible",
    min_score: Annotated[int | None, Query(ge=0, le=100)] = None,
    min_coverage: Annotated[float | None, Query(ge=0, le=1)] = None,
    company_id: UUID | None = None,
    work_mode: WorkMode | None = None,
    q: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    sort: Literal["score", "recent"] = "score",
    offset: Annotated[int, Query(ge=0, le=100000)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> MatchPage:
    filters = service.MatchFilters(
        status=status,
        min_score=min_score,
        min_coverage=min_coverage,
        company_id=company_id,
        work_mode=work_mode,
        q=q.strip() or None if q else None,
        sort=sort,
    )
    return await service.listing(db, principal.user.id, profile_id, filters, offset, limit)


@router.get("/matches/{job_id}", response_model=MatchView)
async def detail(
    profile_id: UUID, job_id: UUID, request: Request, db: SessionDependency, principal: Reader
) -> MatchView:
    return await service.detail(db, principal.user.id, profile_id, job_id, ai_cache_key(request))


@router.get("/match-status", response_model=MatchStatusView)
async def match_status(
    profile_id: UUID, db: SessionDependency, principal: Reader
) -> MatchStatusView:
    return await service.status(db, principal.user.id, profile_id)


@router.post("/matches/recalculate", status_code=202, response_model=MatchRunView)
async def recalculate(
    profile_id: UUID, request: Request, db: SessionDependency, principal: Updater
) -> MatchRunView:
    state = request.app.state
    check_csrf(request, state.settings, str(principal.session.id), state.clock())
    key = await state.rate_limits.consume(
        "match_recalculate",
        str(principal.user.id),
        state.settings.matching_user_hour_limit,
        3600,
        state.clock(),
    )
    try:
        run, created = await service.start_manual(db, principal.user.id, profile_id)
    except Exception:
        await state.rate_limits.refund(key)
        raise
    if not created:
        await state.rate_limits.refund(key)
    return run
