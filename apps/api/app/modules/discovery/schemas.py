from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.urls import source_url

ScanStatus = Literal[
    "queued", "running", "needs_input", "succeeded", "unsupported", "failed", "superseded"
]


class CandidateView(BaseModel):
    id: UUID
    url: str
    hostname: str
    confidence: Literal["low", "medium", "high"]
    evidence: list[str]


class CareerSourceView(BaseModel):
    id: UUID
    url: str
    kind: Literal["generic_page", "ats"]
    platform: str | None
    discovery_method: str
    evidence: list[str]
    created_at: datetime
    updated_at: datetime


class ScanSummary(BaseModel):
    id: UUID
    company_id: UUID
    parent_scan_id: UUID | None
    status: ScanStatus
    selected_url: str | None
    failure_code: str | None
    attempt_count: int
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class ScanView(ScanSummary):
    resolved_website_url: str | None
    resolution_confidence: str | None
    resolution_evidence: list[str]
    candidates: list[CandidateView]
    sources: list[CareerSourceView]


class ScanPage(BaseModel):
    items: list[ScanSummary]
    next_offset: int | None


class ScanSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_id: UUID | None = None
    website_url: Annotated[str, Field(max_length=2048)] | None = None

    @model_validator(mode="after")
    def one_target(self) -> Self:
        if (self.candidate_id is None) == (self.website_url is None):
            raise ValueError("Select exactly one candidate or website URL")
        if self.website_url is not None:
            self.website_url = source_url(self.website_url)
        return self
