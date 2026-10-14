"""Job extraction runs, normalized jobs, and permissions."""

from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_job_extraction"
down_revision: str | None = "0004_career_discovery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = (
    (UUID("bf01ca0b-b788-513a-80c2-db5cbafb2787"), "jobs:read:self"),
    (UUID("5d5dbfdd-294f-50ad-817e-466b76da8be0"), "extractions:create:self"),
)


def upgrade() -> None:
    op.create_table(
        "extraction_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("scan_id", sa.Uuid(), nullable=True),
        sa.Column("trigger", sa.String(length=16), nullable=False),
        sa.Column("stage", sa.String(length=16), server_default="static", nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("strategy", sa.String(length=32), nullable=True),
        sa.Column("confidence", sa.String(length=12), nullable=True),
        sa.Column("jobs_found", sa.Integer(), server_default="0", nullable=False),
        sa.Column("jobs_created", sa.Integer(), server_default="0", nullable=False),
        sa.Column("jobs_updated", sa.Integer(), server_default="0", nullable=False),
        sa.Column("jobs_unchanged", sa.Integer(), server_default="0", nullable=False),
        sa.Column("jobs_closed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("complete", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "confidence IS NULL OR confidence IN ('low','medium','high')",
            name=op.f("ck_extraction_runs_valid_confidence"),
        ),
        sa.CheckConstraint(
            "stage IN ('static','browser')", name=op.f("ck_extraction_runs_valid_stage")
        ),
        sa.CheckConstraint(
            "status IN ('queued','running','succeeded','partial','unsupported','failed')",
            name=op.f("ck_extraction_runs_valid_status"),
        ),
        sa.CheckConstraint(
            "strategy IS NULL OR strategy IN ('ats_api','structured_data','static_html','browser')",
            name=op.f("ck_extraction_runs_valid_strategy"),
        ),
        sa.CheckConstraint(
            "trigger IN ('discovery','manual')", name=op.f("ck_extraction_runs_valid_trigger")
        ),
        sa.CheckConstraint(
            "attempt_count >= 0", name=op.f("ck_extraction_runs_attempts_nonnegative")
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_extraction_runs_company_id_companies"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["scan_id"],
            ["discovery_scans.id"],
            name=op.f("fk_extraction_runs_scan_id_discovery_scans"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["career_sources.id"],
            name=op.f("fk_extraction_runs_source_id_career_sources"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_extraction_runs_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_extraction_runs")),
    )
    op.create_index(
        "ix_runs_owner_created", "extraction_runs", ["user_id", "created_at", "id"], unique=False
    )
    op.create_index("ix_runs_scan", "extraction_runs", ["scan_id"], unique=False)
    op.create_index(
        "ix_runs_source_created", "extraction_runs", ["source_id", "created_at", "id"], unique=False
    )
    op.create_index(
        "uq_runs_active_source",
        "extraction_runs",
        ["source_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued','running')"),
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("dedupe_key", sa.String(length=2100), nullable=False),
        sa.Column("canonical_url", sa.String(length=2048), nullable=False),
        sa.Column("source_job_id", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("location_text", sa.String(length=500), nullable=True),
        sa.Column("work_mode", sa.String(length=16), nullable=False),
        sa.Column("employment_type", sa.String(length=16), nullable=False),
        sa.Column("department", sa.String(length=255), nullable=True),
        sa.Column("description_text", sa.Text(), nullable=True),
        sa.Column("requirements_text", sa.Text(), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_through", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extraction_method", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.String(length=12), nullable=False),
        sa.Column(
            "field_sources",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("duplicate_of_job_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "confidence IN ('low','medium','high')", name=op.f("ck_jobs_valid_confidence")
        ),
        sa.CheckConstraint(
            "employment_type IN ('full_time','part_time','contract','temporary','internship',"
            "'unknown')",
            name=op.f("ck_jobs_valid_employment_type"),
        ),
        sa.CheckConstraint(
            "extraction_method IN ('ats_api','structured_data','static_html','browser')",
            name=op.f("ck_jobs_valid_method"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(field_sources) = 'object'", name=op.f("ck_jobs_field_sources_object")
        ),
        sa.CheckConstraint(
            "work_mode IN ('remote','hybrid','onsite','unknown')",
            name=op.f("ck_jobs_valid_work_mode"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_jobs_company_id_companies"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["duplicate_of_job_id"],
            ["jobs.id"],
            name=op.f("fk_jobs_duplicate_of_job_id_jobs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["career_sources.id"],
            name=op.f("fk_jobs_source_id_career_sources"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_jobs_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
        sa.UniqueConstraint("company_id", "dedupe_key", name="uq_jobs_company_dedupe"),
    )
    op.create_index(
        "ix_jobs_company_fingerprint", "jobs", ["company_id", "fingerprint"], unique=False
    )
    op.create_index("ix_jobs_owner_seen", "jobs", ["user_id", "last_seen_at", "id"], unique=False)
    op.create_index("ix_jobs_source_open", "jobs", ["source_id", "closed_at"], unique=False)
    op.create_table(
        "extraction_outbox",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("publish_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["extraction_runs.id"],
            name=op.f("fk_extraction_outbox_run_id_extraction_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("run_id", name=op.f("pk_extraction_outbox")),
    )
    op.create_index(
        op.f("ix_extraction_outbox_available_at"),
        "extraction_outbox",
        ["available_at"],
        unique=False,
    )
    op.create_table(
        "extraction_run_jobs",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("change", sa.String(length=12), nullable=False),
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "change IN ('created','updated','unchanged')",
            name=op.f("ck_extraction_run_jobs_valid_change"),
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name=op.f("fk_extraction_run_jobs_job_id_jobs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["extraction_runs.id"],
            name=op.f("fk_extraction_run_jobs_run_id_extraction_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("run_id", "job_id", name=op.f("pk_extraction_run_jobs")),
    )
    op.create_index(
        "ix_run_jobs_job", "extraction_run_jobs", ["job_id", "observed_at"], unique=False
    )
    permissions = sa.table(
        "permissions",
        sa.column("id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("description", sa.String()),
    )
    for permission_id, code in PERMISSIONS:
        op.bulk_insert(permissions, [{"id": permission_id, "code": code, "description": code}])
        op.execute(
            sa.text(
                "INSERT INTO role_permissions(role_id, permission_id) "
                "SELECT id, :permission FROM roles WHERE id = :member"
            ).bindparams(permission=permission_id, member=UUID(int=1))
        )


def downgrade() -> None:
    for permission_id, _ in PERMISSIONS:
        op.execute(
            sa.text("DELETE FROM role_permissions WHERE permission_id = :id").bindparams(
                id=permission_id
            )
        )
        op.execute(sa.text("DELETE FROM permissions WHERE id = :id").bindparams(id=permission_id))
    op.drop_index("ix_run_jobs_job", table_name="extraction_run_jobs")
    op.drop_table("extraction_run_jobs")
    op.drop_index(op.f("ix_extraction_outbox_available_at"), table_name="extraction_outbox")
    op.drop_table("extraction_outbox")
    op.drop_index("ix_jobs_source_open", table_name="jobs")
    op.drop_index("ix_jobs_owner_seen", table_name="jobs")
    op.drop_index("ix_jobs_company_fingerprint", table_name="jobs")
    op.drop_table("jobs")
    op.drop_index(
        "uq_runs_active_source",
        table_name="extraction_runs",
        postgresql_where=sa.text("status IN ('queued','running')"),
    )
    op.drop_index("ix_runs_source_created", table_name="extraction_runs")
    op.drop_index("ix_runs_scan", table_name="extraction_runs")
    op.drop_index("ix_runs_owner_created", table_name="extraction_runs")
    op.drop_table("extraction_runs")
