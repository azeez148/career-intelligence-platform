from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError
from app.modules.companies.models import Company
from app.modules.jobs.models import ExtractionRunJob, Job
from app.modules.jobs.schemas import JobObservation, JobPage, JobSummary, JobView

OBSERVATION_LIMIT = 20


@dataclass(frozen=True)
class JobFilters:
    company_id: UUID | None = None
    source_id: UUID | None = None
    q: str | None = None
    work_mode: str | None = None
    employment_type: str | None = None
    status: str = "open"
    include_duplicates: bool = False


def like_pattern(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def summary(job: Job, company_name: str | None) -> JobSummary:
    fields = {key: getattr(job, key) for key in JobSummary.model_fields if key != "company_name"}
    return JobSummary.model_validate(fields | {"company_name": company_name})


def filtered(user_id: UUID, filters: JobFilters) -> Select[tuple[Job, str | None]]:
    statement = (
        select(Job, Company.name)
        .join(Company, Company.id == Job.company_id)
        .where(Job.user_id == user_id)
    )
    if filters.company_id is not None:
        statement = statement.where(Job.company_id == filters.company_id)
    if filters.source_id is not None:
        statement = statement.where(Job.source_id == filters.source_id)
    if filters.work_mode is not None:
        statement = statement.where(Job.work_mode == filters.work_mode)
    if filters.employment_type is not None:
        statement = statement.where(Job.employment_type == filters.employment_type)
    if filters.status == "open":
        statement = statement.where(Job.closed_at.is_(None))
    elif filters.status == "closed":
        statement = statement.where(Job.closed_at.is_not(None))
    if not filters.include_duplicates:
        statement = statement.where(Job.duplicate_of_job_id.is_(None))
    if filters.q:
        pattern = like_pattern(filters.q)
        statement = statement.where(
            or_(
                Job.title.ilike(pattern, escape="\\"),
                Job.department.ilike(pattern, escape="\\"),
            )
        )
    return statement


async def listing(
    db: AsyncSession, user_id: UUID, filters: JobFilters, offset: int, limit: int
) -> JobPage:
    rows = list(
        (
            await db.execute(
                filtered(user_id, filters)
                .order_by(Job.last_seen_at.desc(), Job.id)
                .offset(offset)
                .limit(limit + 1)
            )
        ).all()
    )
    return JobPage(
        items=[summary(job, name) for job, name in rows[:limit]],
        next_offset=offset + limit if len(rows) > limit else None,
    )


async def detail(db: AsyncSession, user_id: UUID, job_id: UUID) -> JobView:
    row = (
        await db.execute(
            select(Job, Company.name)
            .join(Company, Company.id == Job.company_id)
            .where(Job.id == job_id, Job.user_id == user_id)
        )
    ).first()
    if row is None:
        raise DomainError(404, "not_found", "Job not found")
    job, company_name = row
    observations = list(
        (
            await db.scalars(
                select(ExtractionRunJob)
                .where(ExtractionRunJob.job_id == job.id)
                .order_by(ExtractionRunJob.observed_at.desc())
                .limit(OBSERVATION_LIMIT)
            )
        ).all()
    )
    return JobView(
        **summary(job, company_name).model_dump(),
        source_job_id=job.source_job_id,
        description_text=job.description_text,
        requirements_text=job.requirements_text,
        valid_through=job.valid_through,
        field_sources=job.field_sources,
        observations=[
            JobObservation.model_validate(row, from_attributes=True) for row in observations
        ],
    )
