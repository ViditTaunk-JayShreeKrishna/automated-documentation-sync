"""Create durable application records.

Revision ID: 0001_initial
Revises:
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "artefacts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("artefact_type", sa.String(64), nullable=False),
        sa.Column("source_system", sa.String(32), nullable=False),
        sa.Column("configured_scope", sa.String(255), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("location", sa.Text()),
        sa.Column("owner_account_id", sa.String(255)),
        sa.Column("version", sa.String(255)),
        sa.Column("content_digest", sa.String(128)),
        sa.Column("last_detected_change_at", sa.DateTime(timezone=True)),
        sa.Column("last_sync_status", sa.String(32)),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("source_system", "configured_scope", "external_id", name="uq_artefact_identity"),
    )
    op.create_table(
        "dependencies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("source_artefact_id", UUID(as_uuid=True), sa.ForeignKey("artefacts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("dependent_artefact_id", UUID(as_uuid=True), sa.ForeignKey("artefacts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("relationship_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("source_artefact_id", "dependent_artefact_id", "relationship_type", name="uq_dependency"),
        sa.CheckConstraint("source_artefact_id <> dependent_artefact_id", name="ck_dependency_no_self"),
    )
    op.create_table(
        "events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("source_system", sa.String(32), nullable=False),
        sa.Column("source_event_id", sa.String(255), nullable=False),
        sa.Column("normalized_payload", sa.JSON(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("source_system", "source_event_id", name="uq_event_source"),
    )
    op.create_table(
        "jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("operation_type", sa.String(64), nullable=False),
        sa.Column("operation_id", sa.String(255), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("lease_owner", sa.String(255)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("operation_type", "operation_id", name="uq_job_operation"),
    )
    op.create_index("ix_jobs_status_claim", "jobs", ["status", "lease_expires_at"])
    op.create_table(
        "proposals",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("artefact_id", UUID(as_uuid=True), sa.ForeignKey("artefacts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("content_digest", sa.String(128), nullable=False),
        sa.Column("before_content", sa.Text(), nullable=False),
        sa.Column("after_content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("artefact_id", "revision", "content_digest", name="uq_proposal_revision"),
    )
    op.create_table(
        "approvals",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("proposal_id", UUID(as_uuid=True), sa.ForeignKey("proposals.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("account_id", sa.String(255), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("exact_content_digest", sa.String(128), nullable=False),
        sa.Column("source_version", sa.String(255), nullable=False),
        sa.Column("target_version", sa.String(255), nullable=False),
        sa.Column("action_target", sa.String(255), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_table(
        "audit_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("actor_account_id", sa.String(255)),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("source_artefact_id", UUID(as_uuid=True), sa.ForeignKey("artefacts.id", ondelete="SET NULL")),
        sa.Column("target_artefact_id", UUID(as_uuid=True), sa.ForeignKey("artefacts.id", ondelete="SET NULL")),
        sa.Column("source_version", sa.String(255)),
        sa.Column("target_version", sa.String(255)),
        sa.Column("content_digest", sa.String(128)),
        sa.Column("before_content", sa.Text()),
        sa.Column("after_content", sa.Text()),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("audit_records")
    op.drop_table("approvals")
    op.drop_table("proposals")
    op.drop_index("ix_jobs_status_claim", "jobs")
    op.drop_table("jobs")
    op.drop_table("events")
    op.drop_table("dependencies")
    op.drop_table("artefacts")
