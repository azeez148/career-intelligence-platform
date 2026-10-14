from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel

WorkMode = Literal["remote", "hybrid", "onsite", "unknown"]
EmploymentType = Literal["full_time", "part_time", "contract", "temporary", "internship", "unknown"]
Strategy = Literal["ats_api", "structured_data", "static_html", "browser"]
Confidence = Literal["low", "medium", "high"]


class JobSummary(BaseModel):
    id: UUID
    company_id: UUID
    company_name: str | None
    source_id: UUID
    title: str
    canonical_url: str
    location_text: str | None
    work_mode: WorkMode
    employment_type: EmploymentType
    department: str | None
    posted_at: datetime | None
    first_seen_at: datetime
    last_seen_at: datetime
    closed_at: datetime | None
    extraction_method: Strategy
    confidence: Confidence
    duplicate_of_job_id: UUID | None


class JobObservation(BaseModel):
    run_id: UUID
    change: Literal["created", "updated", "unchanged"]
    observed_at: datetime


class JobView(JobSummary):
    source_job_id: str | None
    description_text: str | None
    requirements_text: str | None
    valid_through: datetime | None
    field_sources: dict[str, Any]
    observations: list[JobObservation]


class JobPage(BaseModel):
    items: list[JobSummary]
    next_offset: int | None
