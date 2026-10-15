"""Match-run queueing. Kept free of service imports so preferences and extraction can use it."""

import hashlib
import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.matching.models import MatchingOutbox, MatchRun
from app.modules.preferences.models import PreferenceProfile


def criteria_hash(criteria: dict[str, object]) -> str:
    canonical = json.dumps(criteria, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


async def enqueue_run(
    db: AsyncSession, user_id: UUID, profile_id: UUID, trigger: str
) -> tuple[MatchRun, bool]:
    """Queue a run in the caller's transaction, coalescing into an already waiting run."""
    waiting = await db.scalar(
        select(MatchRun).where(MatchRun.profile_id == profile_id, MatchRun.status == "queued")
    )
    if waiting is not None:
        return waiting, False
    run = MatchRun(user_id=user_id, profile_id=profile_id, trigger=trigger, status="queued")
    try:
        async with db.begin_nested():
            db.add(run)
            await db.flush()
            db.add(MatchingOutbox(run_id=run.id))
            await db.flush()
    except IntegrityError:
        waiting = await db.scalar(
            select(MatchRun).where(MatchRun.profile_id == profile_id, MatchRun.status == "queued")
        )
        if waiting is None:
            raise
        return waiting, False
    return run, True


async def enqueue_for_user(db: AsyncSession, user_id: UUID, trigger: str) -> int:
    profile_ids = (
        await db.scalars(select(PreferenceProfile.id).where(PreferenceProfile.user_id == user_id))
    ).all()
    for profile_id in profile_ids:
        await enqueue_run(db, user_id, profile_id, trigger)
    return len(profile_ids)
