from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError
from app.modules.companies.models import Company
from app.modules.jobs.models import Job
from app.modules.jobs.service import like_pattern
from app.modules.jobs.service import summary as job_summary
from app.modules.matching.models import AIAssessment, JobMatch, MatchRun
from app.modules.matching.queue import criteria_hash, enqueue_run
from app.modules.matching.schemas import (
    AIAssessmentView,
    MatchPage,
    MatchRunView,
    MatchStatusView,
    MatchSummary,
    MatchView,
)
from app.modules.matching.scoring import ALGORITHM_VERSION
from app.modules.preferences.service import owned as owned_profile


async def start_manual(
    db: AsyncSession, user_id: UUID, profile_id: UUID
) -> tuple[MatchRunView, bool]:
    await owned_profile(db, user_id, profile_id)
    run, created = await enqueue_run(db, user_id, profile_id, "manual")
    await db.commit()
    await db.refresh(run)
    return MatchRunView.model_validate(run, from_attributes=True), created


@dataclass(frozen=True)
class MatchFilters:
    status: str = "eligible"
    min_score: int | None = None
    min_coverage: float | None = None
    company_id: UUID | None = None
    work_mode: str | None = None
    q: str | None = None
    sort: str = "score"


def _summary(match: JobMatch, job: Job, company_name: str | None) -> MatchSummary:
    return MatchSummary(
        job=job_summary(job, company_name),
        status=match.status,
        score=match.score,
        coverage=float(match.coverage),
        limited=match.limited,
        summary=str(match.explanation.get("summary", "")),
        computed_at=match.computed_at,
    )


def _filtered(profile_id: UUID, filters: MatchFilters) -> Select[tuple[JobMatch, Job, str | None]]:
    statement = (
        select(JobMatch, Job, Company.name)
        .join(Job, Job.id == JobMatch.job_id)
        .join(Company, Company.id == Job.company_id)
        .where(JobMatch.profile_id == profile_id, Job.closed_at.is_(None))
    )
    if filters.status != "all":
        statement = statement.where(JobMatch.status == filters.status)
    if filters.min_score is not None:
        statement = statement.where(JobMatch.score >= filters.min_score)
    if filters.min_coverage is not None:
        statement = statement.where(JobMatch.coverage >= filters.min_coverage)
    if filters.company_id is not None:
        statement = statement.where(Job.company_id == filters.company_id)
    if filters.work_mode is not None:
        statement = statement.where(Job.work_mode == filters.work_mode)
    if filters.q:
        statement = statement.where(Job.title.ilike(like_pattern(filters.q), escape="\\"))
    if filters.sort == "recent":
        return statement.order_by(Job.last_seen_at.desc(), Job.id)
    return statement.order_by(
        JobMatch.limited, JobMatch.score.desc().nulls_last(), Job.last_seen_at.desc(), Job.id
    )


async def listing(
    db: AsyncSession,
    user_id: UUID,
    profile_id: UUID,
    filters: MatchFilters,
    offset: int,
    limit: int,
) -> MatchPage:
    await owned_profile(db, user_id, profile_id)
    rows = list(
        (await db.execute(_filtered(profile_id, filters).offset(offset).limit(limit + 1))).all()
    )
    return MatchPage(
        items=[_summary(match, job, name) for match, job, name in rows[:limit]],
        next_offset=offset + limit if len(rows) > limit else None,
    )


async def current_assessment(
    db: AsyncSession, match: JobMatch, job: Job, provider: str, model: str, prompt_version: str
) -> AIAssessment | None:
    assessment: AIAssessment | None = await db.scalar(
        select(AIAssessment).where(
            AIAssessment.profile_id == match.profile_id,
            AIAssessment.job_id == job.id,
            AIAssessment.provider == provider,
            AIAssessment.model == model,
            AIAssessment.prompt_version == prompt_version,
            AIAssessment.criteria_hash == match.criteria_hash,
            AIAssessment.job_content_hash == job.content_hash,
        )
    )
    return assessment


async def owned_match(
    db: AsyncSession, user_id: UUID, profile_id: UUID, job_id: UUID
) -> tuple[JobMatch, Job, str | None]:
    await owned_profile(db, user_id, profile_id)
    row = (
        await db.execute(
            select(JobMatch, Job, Company.name)
            .join(Job, Job.id == JobMatch.job_id)
            .join(Company, Company.id == Job.company_id)
            .where(JobMatch.profile_id == profile_id, JobMatch.job_id == job_id)
        )
    ).first()
    if row is None:
        raise DomainError(404, "not_found", "Match not found")
    return row[0], row[1], row[2]


async def detail(
    db: AsyncSession,
    user_id: UUID,
    profile_id: UUID,
    job_id: UUID,
    ai_cache_key: tuple[str, str, str] | None = None,
) -> MatchView:
    match, job, company_name = await owned_match(db, user_id, profile_id, job_id)
    assessment = None
    if ai_cache_key is not None:
        cached = await current_assessment(db, match, job, *ai_cache_key)
        if cached is not None:
            assessment = AIAssessmentView.model_validate(cached, from_attributes=True)
    return MatchView(
        **_summary(match, job, company_name).model_dump(),
        algorithm_version=match.algorithm_version,
        explanation=match.explanation,
        ai_assessment=assessment,
    )


async def status(db: AsyncSession, user_id: UUID, profile_id: UUID) -> MatchStatusView:
    profile = await owned_profile(db, user_id, profile_id)
    latest = await db.scalar(
        select(MatchRun)
        .where(MatchRun.profile_id == profile_id)
        .order_by(MatchRun.created_at.desc(), MatchRun.id)
        .limit(1)
    )
    active = bool(
        await db.scalar(
            select(func.count())
            .select_from(MatchRun)
            .where(MatchRun.profile_id == profile_id, MatchRun.status.in_(("queued", "running")))
        )
    )
    outdated = await db.scalar(
        select(func.count())
        .select_from(JobMatch)
        .join(Job, Job.id == JobMatch.job_id)
        .where(
            JobMatch.profile_id == profile_id,
            or_(
                JobMatch.algorithm_version != ALGORITHM_VERSION,
                JobMatch.criteria_hash != criteria_hash(profile.criteria),
                JobMatch.job_content_hash != Job.content_hash,
            ),
        )
    )
    unscored = await db.scalar(
        select(func.count())
        .select_from(Job)
        .outerjoin(JobMatch, and_(JobMatch.job_id == Job.id, JobMatch.profile_id == profile_id))
        .where(
            Job.user_id == user_id,
            Job.closed_at.is_(None),
            Job.duplicate_of_job_id.is_(None),
            JobMatch.job_id.is_(None),
        )
    )
    return MatchStatusView(
        latest_run=MatchRunView.model_validate(latest, from_attributes=True) if latest else None,
        active=active,
        stale=bool(outdated or unscored),
    )
