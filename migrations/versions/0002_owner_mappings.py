"""Add administrator-managed owner and delegate mappings.

Revision ID: 0002_owner_mappings
Revises: 0001_initial
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0002_owner_mappings"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "owner_mappings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("artefact_id", UUID(as_uuid=True), sa.ForeignKey("artefacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("account_id", sa.String(255), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("delegate", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("artefact_id", "account_id", "role", name="uq_owner_mapping"),
    )
    op.create_index("ix_owner_mapping_lookup", "owner_mappings", ["artefact_id", "account_id", "active"])


def downgrade() -> None:
    op.drop_index("ix_owner_mapping_lookup", "owner_mappings")
    op.drop_table("owner_mappings")
