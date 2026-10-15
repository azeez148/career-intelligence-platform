"""Match runs, persisted matches, AI assessment cache, AI usage, and permissions."""

from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_matching"
down_revision: str | None = "0005_job_extraction"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = (
    (UUID("5231669c-e3fe-5957-b673-c87d4f454ba7"), "matches:read:self"),
    (UUID("89cf06a8-585f-5623-ab25-faab16f1c1a0"), "matches:update:self"),
    (UUID("76e6c954-44e3-5c48-b4f9-210664b4807e"), "ai:use:self"),
)


def upgrade() -> None:
    op.create_table(
        "ai_usage",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("cost", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('succeeded','invalid_output','unavailable','timeout','refused')",
            name=op.f("ck_ai_usage_valid_status"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_ai_usage_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_usage")),
    )
    op.create_index("ix_ai_usage_user_created", "ai_usage", ["user_id", "created_at"], unique=False)
    op.create_table(
        "match_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("trigger", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("jobs_scored", sa.Integer(), server_default="0", nullable=False),
        sa.Column("jobs_unchanged", sa.Integer(), server_default="0", nullable=False),
        sa.Column("jobs_removed", sa.Integer(), server_default="0", nullable=False),
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
            "status IN ('queued','running','succeeded','partial','failed')",
            name=op.f("ck_match_runs_valid_status"),
        ),
        sa.CheckConstraint(
            "trigger IN ('preference_update','jobs_changed','manual')",
            name=op.f("ck_match_runs_valid_trigger"),
        ),
        sa.CheckConstraint("attempt_count >= 0", name=op.f("ck_match_runs_attempts_nonnegative")),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["preference_profiles.id"],
            name=op.f("fk_match_runs_profile_id_preference_profiles"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_match_runs_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_match_runs")),
    )
    op.create_index(
        "ix_match_runs_profile_created",
        "match_runs",
        ["profile_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "uq_match_runs_queued_profile",
        "match_runs",
        ["profile_id"],
        unique=True,
        postgresql_where=sa.text("status = 'queued'"),
    )
    op.create_index(
        "uq_match_runs_running_profile",
        "match_runs",
        ["profile_id"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )
    op.create_table(
        "matching_outbox",
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
            ["match_runs.id"],
            name=op.f("fk_matching_outbox_run_id_match_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("run_id", name=op.f("pk_matching_outbox")),
    )
    op.create_index(
        op.f("ix_matching_outbox_available_at"), "matching_outbox", ["available_at"], unique=False
    )
    op.create_table(
        "ai_assessments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("criteria_hash", sa.String(length=64), nullable=False),
        sa.Column("job_content_hash", sa.String(length=64), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "jsonb_typeof(result) = 'object'", name=op.f("ck_ai_assessments_result_object")
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], name=op.f("fk_ai_assessments_job_id_jobs"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["preference_profiles.id"],
            name=op.f("fk_ai_assessments_profile_id_preference_profiles"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_ai_assessments_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_assessments")),
        sa.UniqueConstraint(
            "profile_id",
            "job_id",
            "provider",
            "model",
            "prompt_version",
            "criteria_hash",
            "job_content_hash",
            name="uq_ai_assessments_cache_key",
        ),
    )
    op.create_table(
        "job_matches",
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("algorithm_version", sa.String(length=32), nullable=False),
        sa.Column("criteria_hash", sa.String(length=64), nullable=False),
        sa.Column("job_content_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("coverage", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("limited", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("explanation", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "jsonb_typeof(explanation) = 'object'", name=op.f("ck_job_matches_explanation_object")
        ),
        sa.CheckConstraint(
            "status IN ('eligible','excluded','insufficient_information')",
            name=op.f("ck_job_matches_valid_status"),
        ),
        sa.CheckConstraint(
            "coverage >= 0 AND coverage <= 1", name=op.f("ck_job_matches_coverage_range")
        ),
        sa.CheckConstraint(
            "score IS NULL OR (score >= 0 AND score <= 100)",
            name=op.f("ck_job_matches_score_range"),
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], name=op.f("fk_job_matches_job_id_jobs"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["preference_profiles.id"],
            name=op.f("fk_job_matches_profile_id_preference_profiles"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_job_matches_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("profile_id", "job_id", name=op.f("pk_job_matches")),
    )
    op.create_index("ix_job_matches_job", "job_matches", ["job_id"], unique=False)
    op.create_index(
        "ix_job_matches_rank",
        "job_matches",
        ["profile_id", "status", "limited", "score", "job_id"],
        unique=False,
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
    op.drop_index("ix_job_matches_rank", table_name="job_matches")
    op.drop_index("ix_job_matches_job", table_name="job_matches")
    op.drop_table("job_matches")
    op.drop_table("ai_assessments")
    op.drop_index(op.f("ix_matching_outbox_available_at"), table_name="matching_outbox")
    op.drop_table("matching_outbox")
    op.drop_index(
        "uq_match_runs_running_profile",
        table_name="match_runs",
        postgresql_where=sa.text("status = 'running'"),
    )
    op.drop_index(
        "uq_match_runs_queued_profile",
        table_name="match_runs",
        postgresql_where=sa.text("status = 'queued'"),
    )
    op.drop_index("ix_match_runs_profile_created", table_name="match_runs")
    op.drop_table("match_runs")
    op.drop_index("ix_ai_usage_user_created", table_name="ai_usage")
    op.drop_table("ai_usage")
