from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.modules.authorization.dependencies import Principal, SessionDependency, require_permission
from app.modules.jobs import service
from app.modules.jobs.schemas import EmploymentType, JobPage, JobView, WorkMode

router = APIRouter(tags=["jobs"])
Reader = Annotated[Principal, Depends(require_permission("jobs:read:self"))]


@router.get("/jobs", response_model=JobPage)
async def listing(
    db: SessionDependency,
    principal: Reader,
    company_id: UUID | None = None,
    source_id: UUID | None = None,
    q: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    work_mode: WorkMode | None = None,
    employment_type: EmploymentType | None = None,
    status: Literal["open", "closed", "all"] = "open",
    include_duplicates: bool = False,
    offset: Annotated[int, Query(ge=0, le=100000)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> JobPage:
    filters = service.JobFilters(
        company_id=company_id,
        source_id=source_id,
        q=q.strip() or None if q else None,
        work_mode=work_mode,
        employment_type=employment_type,
        status=status,
        include_duplicates=include_duplicates,
    )
    return await service.listing(db, principal.user.id, filters, offset, limit)


@router.get("/jobs/{job_id}", response_model=JobView)
async def detail(job_id: UUID, db: SessionDependency, principal: Reader) -> JobView:
    return await service.detail(db, principal.user.id, job_id)
