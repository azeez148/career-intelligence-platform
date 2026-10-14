from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

RUN_STATUSES = ("queued", "running", "succeeded", "partial", "unsupported", "failed")
STRATEGIES = ("ats_api", "structured_data", "static_html", "browser")


class ExtractionRun(Base):
    __tablename__ = "extraction_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','succeeded','partial','unsupported','failed')",
            name="valid_status",
        ),
        CheckConstraint("trigger IN ('discovery','manual')", name="valid_trigger"),
        CheckConstraint("stage IN ('static','browser')", name="valid_stage"),
        CheckConstraint(
            "strategy IS NULL OR strategy IN ('ats_api','structured_data','static_html','browser')",
            name="valid_strategy",
        ),
        CheckConstraint(
            "confidence IS NULL OR confidence IN ('low','medium','high')",
            name="valid_confidence",
        ),
        CheckConstraint("attempt_count >= 0", name="attempts_nonnegative"),
        Index("ix_runs_owner_created", "user_id", "created_at", "id"),
        Index("ix_runs_source_created", "source_id", "created_at", "id"),
        Index("ix_runs_scan", "scan_id"),
        Index(
            "uq_runs_active_source",
            "source_id",
            unique=True,
            postgresql_where=text("status IN ('queued','running')"),
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    source_id: Mapped[UUID] = mapped_column(ForeignKey("career_sources.id", ondelete="CASCADE"))
    scan_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("discovery_scans.id", ondelete="SET NULL")
    )
    trigger: Mapped[str] = mapped_column(String(16))
    stage: Mapped[str] = mapped_column(String(16), default="static", server_default="static")
    status: Mapped[str] = mapped_column(String(24))
    strategy: Mapped[str | None] = mapped_column(String(32))
    confidence: Mapped[str | None] = mapped_column(String(12))
    jobs_found: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    jobs_created: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    jobs_updated: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    jobs_unchanged: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    jobs_closed: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    complete: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
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


class ExtractionOutbox(Base):
    __tablename__ = "extraction_outbox"
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("extraction_runs.id", ondelete="CASCADE"), primary_key=True
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    publish_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
