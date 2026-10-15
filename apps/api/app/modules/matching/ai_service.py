"""On-demand advisory AI assessments. Never modifies deterministic matches or jobs."""

import logging
from datetime import datetime, timedelta
from time import perf_counter
from typing import Literal
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import DomainError
from app.integrations.ai.provider import AIError, AIProvider, AssessmentRequest, Usage
from app.modules.matching.models import AIAssessment, AIUsage
from app.modules.matching.schemas import AIAssessmentView
from app.modules.matching.service import current_assessment, owned_match
from app.modules.preferences.models import PreferenceProfile

logger = logging.getLogger(__name__)
WINDOW = timedelta(hours=24)
MESSAGES = {
    "succeeded": "AI assessment ready.",
    "cached": "AI assessment ready.",
    "invalid_output": "The AI response did not pass validation, so it was discarded.",
    "unavailable": "The AI service is unavailable right now. Your match is unchanged.",
    "timeout": "The AI service did not respond in time. Your match is unchanged.",
    "refused": "The AI service declined to assess this job. Your match is unchanged.",
}


class AIAssessmentResponse(BaseModel):
    status: Literal["succeeded", "cached", "invalid_output", "unavailable", "timeout", "refused"]
    message: str
    assessment: AIAssessmentView | None
    remaining_today: int


class AIStatusView(BaseModel):
    enabled: bool
    daily_limit: int
    remaining_today: int


async def remaining(db: AsyncSession, user_id: UUID, settings: Settings, now: datetime) -> int:
    used = await db.scalar(
        select(func.count())
        .select_from(AIUsage)
        .where(AIUsage.user_id == user_id, AIUsage.created_at > now - WINDOW)
    )
    return max(settings.ai_user_daily_limit - int(used or 0), 0)


async def status(
    db: AsyncSession, user_id: UUID, provider: AIProvider, settings: Settings, now: datetime
) -> AIStatusView:
    return AIStatusView(
        enabled=provider.enabled,
        daily_limit=settings.ai_user_daily_limit,
        remaining_today=await remaining(db, user_id, settings, now) if provider.enabled else 0,
    )


async def assess(
    db: AsyncSession,
    user_id: UUID,
    profile_id: UUID,
    job_id: UUID,
    provider: AIProvider,
    settings: Settings,
    now: datetime,
) -> AIAssessmentResponse:
    if not provider.enabled:
        raise DomainError(403, "ai_disabled", "AI assessments are not enabled")
    match, job, _ = await owned_match(db, user_id, profile_id, job_id)
    cached = await current_assessment(db, match, job, *provider.cache_key())
    if cached is not None:
        return AIAssessmentResponse(
            status="cached",
            message=MESSAGES["cached"],
            assessment=AIAssessmentView.model_validate(cached, from_attributes=True),
            remaining_today=await remaining(db, user_id, settings, now),
        )
    if await remaining(db, user_id, settings, now) <= 0:
        raise DomainError(429, "ai_daily_limit", "Daily AI assessment limit reached")
    profile = await db.get(PreferenceProfile, profile_id)
    assert profile is not None
    request = AssessmentRequest(
        title=job.title,
        location_text=job.location_text,
        work_mode=job.work_mode,
        employment_type=job.employment_type,
        description_text=job.description_text,
        requirements_text=job.requirements_text,
        criteria=profile.criteria,
    )
    start = perf_counter()
    result_status = "succeeded"
    view: AIAssessmentView | None = None
    try:
        outcome = await provider.assess(request)
        usage = outcome.usage
        row = await db.scalar(
            insert(AIAssessment)
            .values(
                user_id=user_id,
                profile_id=profile_id,
                job_id=job.id,
                provider=provider.name,
                model=provider.model,
                prompt_version=provider.prompt_version,
                criteria_hash=match.criteria_hash,
                job_content_hash=job.content_hash,
                result=outcome.assessment.model_dump(),
                created_at=now,
            )
            .on_conflict_do_nothing(constraint="uq_ai_assessments_cache_key")
            .returning(AIAssessment)
        )
        stored = row or await current_assessment(db, match, job, *provider.cache_key())
        if stored is not None:
            view = AIAssessmentView.model_validate(stored, from_attributes=True)
    except AIError as error:
        result_status = error.status
        usage = getattr(error, "usage", Usage(int((perf_counter() - start) * 1000)))
        logger.warning("ai_assessment_failed", extra={"code": error.code})
    db.add(
        AIUsage(
            user_id=user_id,
            purpose="match_assessment",
            provider=provider.name,
            model=provider.model,
            status=result_status,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
            cost=usage.cost,
            latency_ms=usage.latency_ms,
            created_at=now,
        )
    )
    await db.commit()
    return AIAssessmentResponse(
        status=result_status,
        message=MESSAGES[result_status],
        assessment=view,
        remaining_today=await remaining(db, user_id, settings, now),
    )
