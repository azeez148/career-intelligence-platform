"""Worker-side recomputation of one profile's matches inside the caller's transaction."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.jobs.models import Job
from app.modules.matching.explain import to_document
from app.modules.matching.models import JobMatch
from app.modules.matching.queue import criteria_hash
from app.modules.matching.scoring import ALGORITHM_VERSION, JobFacts, score
from app.modules.preferences.models import PreferenceProfile
from app.modules.preferences.schemas import Criteria

BATCH = 200
MAX_JOBS = 5000


@dataclass
class RecomputeCounts:
    scored: int = 0
    unchanged: int = 0
    removed: int = 0
    complete: bool = True


def facts(job: Job) -> JobFacts:
    return JobFacts(
        title=job.title,
        department=job.department,
        location_text=job.location_text,
        work_mode=job.work_mode,
        employment_type=job.employment_type,
        description_text=job.description_text,
        requirements_text=job.requirements_text,
        confidence=job.confidence,
    )


async def recompute(
    db: AsyncSession, profile: PreferenceProfile, now: datetime, max_jobs: int = MAX_JOBS
) -> RecomputeCounts:
    criteria = Criteria.model_validate(profile.criteria)
    digest = criteria_hash(profile.criteria)
    counts = RecomputeCounts()
    removed = await db.execute(
        delete(JobMatch)
        .where(
            JobMatch.profile_id == profile.id,
            JobMatch.job_id.in_(
                select(Job.id).where(
                    or_(Job.closed_at.is_not(None), Job.duplicate_of_job_id.is_not(None))
                )
            ),
        )
        .returning(JobMatch.job_id)
    )
    counts.removed = len(removed.all())
    existing = {
        row.job_id: (row.algorithm_version, row.criteria_hash, row.job_content_hash)
        for row in (
            await db.execute(
                select(
                    JobMatch.job_id,
                    JobMatch.algorithm_version,
                    JobMatch.criteria_hash,
                    JobMatch.job_content_hash,
                ).where(JobMatch.profile_id == profile.id)
            )
        ).all()
    }
    last_id: UUID | None = None
    seen = 0
    while True:
        statement = (
            select(Job)
            .where(
                Job.user_id == profile.user_id,
                Job.closed_at.is_(None),
                Job.duplicate_of_job_id.is_(None),
            )
            .order_by(Job.id)
            .limit(BATCH)
        )
        if last_id is not None:
            statement = statement.where(Job.id > last_id)
        jobs = list((await db.scalars(statement)).all())
        if not jobs:
            break
        for job in jobs:
            if seen >= max_jobs:
                counts.complete = False
                return counts
            seen += 1
            if existing.get(job.id) == (ALGORITHM_VERSION, digest, job.content_hash):
                counts.unchanged += 1
                continue
            result = score(criteria, facts(job))
            values = {
                "user_id": profile.user_id,
                "algorithm_version": result.algorithm_version,
                "criteria_hash": digest,
                "job_content_hash": job.content_hash,
                "status": result.status,
                "score": result.score,
                "coverage": Decimal(result.coverage.numerator)
                / Decimal(result.coverage.denominator),
                "limited": "limited_information" in result.flags,
                "explanation": to_document(result),
                "computed_at": now,
            }
            await db.execute(
                insert(JobMatch)
                .values(profile_id=profile.id, job_id=job.id, **values)
                .on_conflict_do_update(index_elements=["profile_id", "job_id"], set_=values)
            )
            counts.scored += 1
        last_id = jobs[-1].id
    return counts
