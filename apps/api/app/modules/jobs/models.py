from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

WORK_MODES = ("remote", "hybrid", "onsite", "unknown")
EMPLOYMENT_TYPES = ("full_time", "part_time", "contract", "temporary", "internship", "unknown")


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(
            "work_mode IN ('remote','hybrid','onsite','unknown')", name="valid_work_mode"
        ),
        CheckConstraint(
            "employment_type IN ('full_time','part_time','contract','temporary','internship',"
            "'unknown')",
            name="valid_employment_type",
        ),
        CheckConstraint(
            "extraction_method IN ('ats_api','structured_data','static_html','browser')",
            name="valid_method",
        ),
        CheckConstraint("confidence IN ('low','medium','high')", name="valid_confidence"),
        CheckConstraint("jsonb_typeof(field_sources) = 'object'", name="field_sources_object"),
        UniqueConstraint("company_id", "dedupe_key", name="uq_jobs_company_dedupe"),
        Index("ix_jobs_owner_seen", "user_id", "last_seen_at", "id"),
        Index("ix_jobs_company_fingerprint", "company_id", "fingerprint"),
        Index("ix_jobs_source_open", "source_id", "closed_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    source_id: Mapped[UUID] = mapped_column(ForeignKey("career_sources.id", ondelete="CASCADE"))
    dedupe_key: Mapped[str] = mapped_column(String(2100))
    canonical_url: Mapped[str] = mapped_column(String(2048))
    source_job_id: Mapped[str | None] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(500))
    location_text: Mapped[str | None] = mapped_column(String(500))
    work_mode: Mapped[str] = mapped_column(String(16), default="unknown")
    employment_type: Mapped[str] = mapped_column(String(16), default="unknown")
    department: Mapped[str | None] = mapped_column(String(255))
    description_text: Mapped[str | None] = mapped_column(Text)
    requirements_text: Mapped[str | None] = mapped_column(Text)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_through: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    extraction_method: Mapped[str] = mapped_column(String(32))
    confidence: Mapped[str] = mapped_column(String(12))
    field_sources: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    content_hash: Mapped[str] = mapped_column(String(64))
    fingerprint: Mapped[str] = mapped_column(String(64))
    duplicate_of_job_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ExtractionRunJob(Base):
    __tablename__ = "extraction_run_jobs"
    __table_args__ = (
        CheckConstraint("change IN ('created','updated','unchanged')", name="valid_change"),
        Index("ix_run_jobs_job", "job_id", "observed_at"),
    )
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("extraction_runs.id", ondelete="CASCADE"), primary_key=True
    )
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True
    )
    change: Mapped[str] = mapped_column(String(12))
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
