import hashlib
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError
from app.core.values import comparison_key
from app.modules.matching.queue import enqueue_run as enqueue_match_run
from app.modules.preferences.models import PreferenceProfile
from app.modules.preferences.schemas import (
    Criteria,
    PreferenceInput,
    PreferencePage,
    PreferenceSummary,
    PreferenceView,
)


def summary(profile: PreferenceProfile) -> PreferenceSummary:
    return PreferenceSummary(
        id=profile.id,
        name=profile.name,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


def view(profile: PreferenceProfile) -> PreferenceView:
    return PreferenceView(
        **summary(profile).model_dump(), criteria=Criteria.model_validate(profile.criteria)
    )


async def owned(db: AsyncSession, user_id: UUID, profile_id: UUID) -> PreferenceProfile:
    profile = await db.scalar(
        select(PreferenceProfile).where(
            PreferenceProfile.id == profile_id, PreferenceProfile.user_id == user_id
        )
    )
    if profile is None:
        raise DomainError(404, "not_found", "Preference profile not found")
    return profile


async def listing(db: AsyncSession, user_id: UUID, offset: int, limit: int) -> PreferencePage:
    rows = list(
        (
            await db.scalars(
                select(PreferenceProfile)
                .where(PreferenceProfile.user_id == user_id)
                .order_by(PreferenceProfile.created_at.desc(), PreferenceProfile.id)
                .offset(offset)
                .limit(limit + 1)
            )
        ).all()
    )
    return PreferencePage(
        items=[summary(row) for row in rows[:limit]],
        next_offset=offset + limit if len(rows) > limit else None,
    )


async def save(
    db: AsyncSession, user_id: UUID, data: PreferenceInput, profile_id: UUID | None = None
) -> PreferenceView:
    profile = (
        await owned(db, user_id, profile_id) if profile_id else PreferenceProfile(user_id=user_id)
    )
    profile.name = data.name
    profile.name_key = hashlib.sha256(comparison_key(data.name).encode()).hexdigest()
    profile.criteria = data.criteria.model_dump(mode="json")
    db.add(profile)
    try:
        await db.flush()
        await db.refresh(profile)
        result = view(profile)
        await enqueue_match_run(db, user_id, profile.id, "preference_update")
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        if getattr(error.orig, "sqlstate", None) == "23505":
            raise DomainError(
                409, "preference_duplicate", "This profile name is already used"
            ) from None
        raise
    return result


async def remove(db: AsyncSession, user_id: UUID, profile_id: UUID) -> None:
    await db.delete(await owned(db, user_id, profile_id))
    await db.commit()
