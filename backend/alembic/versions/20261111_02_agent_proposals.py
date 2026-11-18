"""Add reviewable coding-agent proposals.

Revision ID: 20261111_02
"""

from alembic import op
import sqlalchemy as sa

revision = "20261111_02"
down_revision = "20261110_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_proposals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("instruction", sa.String(length=2000), nullable=False),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("summary", sa.String(length=500), nullable=False),
        sa.Column("original_content", sa.Text(), nullable=False),
        sa.Column("proposed_content", sa.Text(), nullable=False),
        sa.Column("original_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_agent_proposals_status", "agent_proposals", ["status"])


def downgrade() -> None:
    op.drop_index("ix_agent_proposals_status", table_name="agent_proposals")
    op.drop_table("agent_proposals")
