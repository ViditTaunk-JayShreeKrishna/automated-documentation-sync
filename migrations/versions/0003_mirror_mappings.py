"""Add authoritative artefact mirror mappings.

Revision ID: 0003_mirror_mappings
Revises: 0002_owner_mappings
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0003_mirror_mappings"
down_revision = "0002_owner_mappings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mirror_mappings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("source_artefact_id", UUID(as_uuid=True), sa.ForeignKey("artefacts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("target_artefact_id", UUID(as_uuid=True), sa.ForeignKey("artefacts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_version", sa.String(255)),
        sa.Column("target_version", sa.String(255)),
        sa.Column("source_digest", sa.String(128)),
        sa.Column("target_digest", sa.String(128)),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("source_artefact_id", "target_artefact_id", name="uq_mirror_mapping"),
    )


def downgrade() -> None:
    op.drop_table("mirror_mappings")
