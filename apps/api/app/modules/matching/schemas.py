from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel

from app.modules.jobs.schemas import JobSummary

MatchStatus = Literal["eligible", "excluded", "insufficient_information"]


class MatchSummary(BaseModel):
    job: JobSummary
    status: MatchStatus
    score: int | None
    coverage: float
    limited: bool
    summary: str
    computed_at: datetime


class MatchPage(BaseModel):
    items: list[MatchSummary]
    next_offset: int | None


class AIAssessmentView(BaseModel):
    model: str
    created_at: datetime
    result: dict[str, Any]


class MatchView(MatchSummary):
    algorithm_version: str
    explanation: dict[str, Any]
    ai_assessment: AIAssessmentView | None


class MatchRunView(BaseModel):
    id: UUID
    trigger: Literal["preference_update", "jobs_changed", "manual"]
    status: Literal["queued", "running", "succeeded", "partial", "failed"]
    jobs_scored: int
    jobs_unchanged: int
    jobs_removed: int
    failure_code: str | None
    created_at: datetime
    completed_at: datetime | None


class MatchStatusView(BaseModel):
    latest_run: MatchRunView | None
    active: bool
    stale: bool
