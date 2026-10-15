from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MatchRun(Base):
    __tablename__ = "match_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','succeeded','partial','failed')", name="valid_status"
        ),
        CheckConstraint(
            "trigger IN ('preference_update','jobs_changed','manual')", name="valid_trigger"
        ),
        CheckConstraint("attempt_count >= 0", name="attempts_nonnegative"),
        Index("ix_match_runs_profile_created", "profile_id", "created_at", "id"),
        # At most one waiting and one running run per profile; bursts coalesce into the
        # waiting run while a running one finishes.
        Index(
            "uq_match_runs_queued_profile",
            "profile_id",
            unique=True,
            postgresql_where=text("status = 'queued'"),
        ),
        Index(
            "uq_match_runs_running_profile",
            "profile_id",
            unique=True,
            postgresql_where=text("status = 'running'"),
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("preference_profiles.id", ondelete="CASCADE")
    )
    trigger: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(16))
    jobs_scored: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    jobs_unchanged: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    jobs_removed: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MatchingOutbox(Base):
    __tablename__ = "matching_outbox"
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("match_runs.id", ondelete="CASCADE"), primary_key=True
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    publish_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class JobMatch(Base):
    __tablename__ = "job_matches"
    __table_args__ = (
        CheckConstraint(
            "status IN ('eligible','excluded','insufficient_information')", name="valid_status"
        ),
        CheckConstraint("score IS NULL OR (score >= 0 AND score <= 100)", name="score_range"),
        CheckConstraint("coverage >= 0 AND coverage <= 1", name="coverage_range"),
        CheckConstraint("jsonb_typeof(explanation) = 'object'", name="explanation_object"),
        Index("ix_job_matches_rank", "profile_id", "status", "limited", "score", "job_id"),
        Index("ix_job_matches_job", "job_id"),
    )
    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("preference_profiles.id", ondelete="CASCADE"), primary_key=True
    )
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    algorithm_version: Mapped[str] = mapped_column(String(32))
    criteria_hash: Mapped[str] = mapped_column(String(64))
    job_content_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    score: Mapped[int | None] = mapped_column(Integer)
    coverage: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    limited: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    explanation: Mapped[dict[str, Any]] = mapped_column(JSONB)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AIAssessment(Base):
    """Cached successful advisory assessments. Never used to change deterministic results."""

    __tablename__ = "ai_assessments"
    __table_args__ = (
        UniqueConstraint(
            "profile_id",
            "job_id",
            "provider",
            "model",
            "prompt_version",
            "criteria_hash",
            "job_content_hash",
            name="uq_ai_assessments_cache_key",
        ),
        CheckConstraint("jsonb_typeof(result) = 'object'", name="result_object"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("preference_profiles.id", ondelete="CASCADE")
    )
    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(200))
    prompt_version: Mapped[str] = mapped_column(String(32))
    criteria_hash: Mapped[str] = mapped_column(String(64))
    job_content_hash: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AIUsage(Base):
    __tablename__ = "ai_usage"
    __table_args__ = (
        CheckConstraint(
            "status IN ('succeeded','invalid_output','unavailable','timeout','refused')",
            name="valid_status",
        ),
        Index("ix_ai_usage_user_created", "user_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    purpose: Mapped[str] = mapped_column(String(32))
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(24))
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    total_tokens: Mapped[int | None] = mapped_column(Integer)
    cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    latency_ms: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
