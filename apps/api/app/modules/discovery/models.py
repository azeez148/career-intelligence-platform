from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DiscoveryScan(Base):
    __tablename__ = "discovery_scans"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','needs_input','succeeded','unsupported','failed',"
            "'superseded')",
            name="valid_status",
        ),
        CheckConstraint("attempt_count >= 0", name="attempts_nonnegative"),
        Index("ix_scans_owner_created", "user_id", "created_at", "id"),
        Index("ix_scans_company_created", "company_id", "created_at", "id"),
        Index(
            "uq_scans_active_company",
            "company_id",
            unique=True,
            postgresql_where=text("status IN ('queued','running','needs_input')"),
        ),
        UniqueConstraint("parent_scan_id", name="uq_scans_parent"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    parent_scan_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("discovery_scans.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(24))
    selected_url: Mapped[str | None] = mapped_column(String(2048))
    resolved_website_url: Mapped[str | None] = mapped_column(String(2048))
    resolution_confidence: Mapped[str | None] = mapped_column(String(24))
    resolution_evidence: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
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


class DiscoveryCandidate(Base):
    __tablename__ = "discovery_candidates"
    __table_args__ = (
        CheckConstraint("confidence IN ('low','medium','high')", name="valid_confidence"),
        CheckConstraint("jsonb_typeof(evidence) = 'array'", name="evidence_array"),
        UniqueConstraint("scan_id", "url", name="uq_candidates_scan_url"),
        Index("ix_candidates_scan", "scan_id", "id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    scan_id: Mapped[UUID] = mapped_column(ForeignKey("discovery_scans.id", ondelete="CASCADE"))
    url: Mapped[str] = mapped_column(String(2048))
    hostname: Mapped[str] = mapped_column(String(253))
    confidence: Mapped[str] = mapped_column(String(12))
    evidence: Mapped[list[str]] = mapped_column(JSONB)


class CareerSource(Base):
    __tablename__ = "career_sources"
    __table_args__ = (
        CheckConstraint("kind IN ('generic_page','ats')", name="valid_kind"),
        CheckConstraint("jsonb_typeof(evidence) = 'array'", name="evidence_array"),
        UniqueConstraint("company_id", "url", name="uq_sources_company_url"),
        Index("ix_sources_owner_company", "user_id", "company_id", "created_at", "id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    scan_id: Mapped[UUID] = mapped_column(ForeignKey("discovery_scans.id", ondelete="CASCADE"))
    url: Mapped[str] = mapped_column(String(2048))
    kind: Mapped[str] = mapped_column(String(24))
    platform: Mapped[str | None] = mapped_column(String(32))
    discovery_method: Mapped[str] = mapped_column(String(32))
    evidence: Mapped[list[str]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ScanOutbox(Base):
    __tablename__ = "scan_outbox"
    scan_id: Mapped[UUID] = mapped_column(
        ForeignKey("discovery_scans.id", ondelete="CASCADE"), primary_key=True
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    publish_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
