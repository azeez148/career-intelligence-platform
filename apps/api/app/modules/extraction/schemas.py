from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.modules.jobs.schemas import Confidence, Strategy

RunStatus = Literal["queued", "running", "succeeded", "partial", "unsupported", "failed"]


class ExtractionRunView(BaseModel):
    id: UUID
    company_id: UUID
    source_id: UUID
    scan_id: UUID | None
    trigger: Literal["discovery", "manual"]
    stage: Literal["static", "browser"]
    status: RunStatus
    strategy: Strategy | None
    confidence: Confidence | None
    jobs_found: int
    jobs_created: int
    jobs_updated: int
    jobs_unchanged: int
    jobs_closed: int
    complete: bool
    attempt_count: int
    failure_code: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
