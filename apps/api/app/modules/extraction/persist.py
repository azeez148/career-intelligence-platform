"""Persist normalized jobs for one extraction run inside the caller's transaction."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.extraction.models import ExtractionRun
from app.modules.jobs.models import ExtractionRunJob, Job
from app.modules.jobs.normalize import CONFIDENCE_RANK, NormalizedJob

FIELDS = (
    "canonical_url",
    "source_job_id",
    "title",
    "location_text",
    "work_mode",
    "employment_type",
    "department",
    "description_text",
    "requirements_text",
    "posted_at",
    "valid_through",
    "extraction_method",
    "confidence",
    "field_sources",
)


@dataclass
class PersistCounts:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    closed: int = 0


def _values(job: NormalizedJob) -> dict[str, object]:
    return {name: getattr(job, name) for name in FIELDS} | {
        "content_hash": job.content_hash(),
        "fingerprint": job.fingerprint(),
    }


async def persist_jobs(
    db: AsyncSession,
    run: ExtractionRun,
    platform: str | None,
    jobs: list[NormalizedJob],
    complete: bool,
    now: datetime,
) -> PersistCounts:
    counts = PersistCounts()
    unique: dict[str, NormalizedJob] = {}
    for job in jobs:
        unique.setdefault(job.dedupe_key(platform), job)
    seen: list[UUID] = []
    for key in sorted(unique):
        job = unique[key]
        values = _values(job)
        created_id = await db.scalar(
            insert(Job)
            .values(
                user_id=run.user_id,
                company_id=run.company_id,
                source_id=run.source_id,
                dedupe_key=key,
                first_seen_at=now,
                last_seen_at=now,
                **values,
            )
            .on_conflict_do_nothing(constraint="uq_jobs_company_dedupe")
            .returning(Job.id)
        )
        if created_id is not None:
            change, job_id = "created", created_id
        else:
            existing = await db.scalar(
                select(Job)
                .where(Job.company_id == run.company_id, Job.dedupe_key == key)
                .with_for_update()
            )
            assert existing is not None
            change = "unchanged" if existing.content_hash == values["content_hash"] else "updated"
            if change == "updated":
                for name, value in values.items():
                    setattr(existing, name, value)
            existing.source_id = run.source_id
            existing.last_seen_at = now
            existing.closed_at = None
            job_id = existing.id
        setattr(counts, change, getattr(counts, change) + 1)
        seen.append(job_id)
        await db.execute(
            insert(ExtractionRunJob)
            .values(run_id=run.id, job_id=job_id, change=change, observed_at=now)
            .on_conflict_do_nothing()
        )
    await db.flush()
    if complete:
        closed = list(
            (
                await db.scalars(
                    update(Job)
                    .where(
                        Job.source_id == run.source_id,
                        Job.closed_at.is_(None),
                        Job.id.not_in(seen) if seen else Job.id.is_not(None),
                    )
                    .values(closed_at=now)
                    .returning(Job.id)
                )
            ).all()
        )
        counts.closed = len(closed)
        if closed:
            await db.execute(
                update(Job)
                .where(Job.duplicate_of_job_id.in_(closed))
                .values(duplicate_of_job_id=None)
            )
    await mark_duplicates(db, run.company_id, {unique[key].fingerprint() for key in unique})
    return counts


async def mark_duplicates(db: AsyncSession, company_id: UUID, fingerprints: set[str]) -> None:
    """Hide lower-confidence copies of the same open job found through another source."""
    if not fingerprints:
        return
    rows = list(
        (
            await db.scalars(
                select(Job)
                .where(
                    Job.company_id == company_id,
                    Job.fingerprint.in_(fingerprints),
                    Job.closed_at.is_(None),
                )
                .order_by(Job.first_seen_at, Job.id)
            )
        ).all()
    )
    groups: dict[str, list[Job]] = {}
    for row in rows:
        groups.setdefault(row.fingerprint, []).append(row)
    for group in groups.values():
        canonical = max(group, key=lambda row: CONFIDENCE_RANK[row.confidence])
        for row in group:
            if row.source_id == canonical.source_id:
                row.duplicate_of_job_id = None
            else:
                row.duplicate_of_job_id = canonical.id
