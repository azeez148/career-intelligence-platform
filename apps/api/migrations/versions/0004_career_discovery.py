"""Asynchronous career-source discovery state and permissions."""

from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_career_discovery"
down_revision: str | None = "0003_companies_preferences"
branch_labels: str | None = None
depends_on: str | None = None

PERMISSIONS = (
    (UUID("0c602e96-b2f0-5f7b-99bb-636c20ef4e80"), "scans:read:self"),
    (UUID("363489db-bc10-55d1-a4db-79a8457c76aa"), "scans:create:self"),
    (UUID("5f296954-d876-589f-b0b6-63928b325dc5"), "scans:update:self"),
)


def upgrade() -> None:
    op.create_table(
        "discovery_scans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("parent_scan_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("selected_url", sa.String(length=2048), nullable=True),
        sa.Column("resolved_website_url", sa.String(length=2048), nullable=True),
        sa.Column("resolution_confidence", sa.String(length=24), nullable=True),
        sa.Column(
            "resolution_evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
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
            "attempt_count >= 0", name=op.f("ck_discovery_scans_attempts_nonnegative")
        ),
        sa.CheckConstraint(
            "status IN ('queued','running','needs_input','succeeded','unsupported','failed',"
            "'superseded')",
            name=op.f("ck_discovery_scans_valid_status"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_discovery_scans_company_id_companies"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_scan_id"],
            ["discovery_scans.id"],
            name=op.f("fk_discovery_scans_parent_scan_id_discovery_scans"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_discovery_scans_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_discovery_scans")),
        sa.UniqueConstraint("parent_scan_id", name="uq_scans_parent"),
    )
    op.create_index(
        "ix_scans_owner_created",
        "discovery_scans",
        ["user_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_scans_company_created",
        "discovery_scans",
        ["company_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "uq_scans_active_company",
        "discovery_scans",
        ["company_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued','running','needs_input')"),
    )
    op.create_table(
        "discovery_candidates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scan_id", sa.Uuid(), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("hostname", sa.String(length=253), nullable=False),
        sa.Column("confidence", sa.String(length=12), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "confidence IN ('low','medium','high')",
            name=op.f("ck_discovery_candidates_valid_confidence"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(evidence) = 'array'",
            name=op.f("ck_discovery_candidates_evidence_array"),
        ),
        sa.ForeignKeyConstraint(
            ["scan_id"],
            ["discovery_scans.id"],
            name=op.f("fk_discovery_candidates_scan_id_discovery_scans"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_discovery_candidates")),
        sa.UniqueConstraint("scan_id", "url", name="uq_candidates_scan_url"),
    )
    op.create_index("ix_candidates_scan", "discovery_candidates", ["scan_id", "id"], unique=False)
    op.create_table(
        "career_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("scan_id", sa.Uuid(), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=True),
        sa.Column("discovery_method", sa.String(length=32), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
            "kind IN ('generic_page','ats')", name=op.f("ck_career_sources_valid_kind")
        ),
        sa.CheckConstraint(
            "jsonb_typeof(evidence) = 'array'",
            name=op.f("ck_career_sources_evidence_array"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_career_sources_company_id_companies"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["scan_id"],
            ["discovery_scans.id"],
            name=op.f("fk_career_sources_scan_id_discovery_scans"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_career_sources_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_career_sources")),
        sa.UniqueConstraint("company_id", "url", name="uq_sources_company_url"),
    )
    op.create_index(
        "ix_sources_owner_company",
        "career_sources",
        ["user_id", "company_id", "created_at", "id"],
        unique=False,
    )
    op.create_table(
        "scan_outbox",
        sa.Column("scan_id", sa.Uuid(), nullable=False),
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
            ["scan_id"],
            ["discovery_scans.id"],
            name=op.f("fk_scan_outbox_scan_id_discovery_scans"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("scan_id", name=op.f("pk_scan_outbox")),
    )
    op.create_index(
        op.f("ix_scan_outbox_available_at"), "scan_outbox", ["available_at"], unique=False
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
    op.drop_table("scan_outbox")
    op.drop_table("career_sources")
    op.drop_table("discovery_candidates")
    op.drop_table("discovery_scans")
