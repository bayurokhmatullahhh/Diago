"""Persist assistant conversations and action history.

Revision ID: 20261121_03
"""

from alembic import op
import sqlalchemy as sa

revision = "20261121_03"
down_revision = "20261111_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_conversations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("messages", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_chat_conversations_updated_at",
        "chat_conversations",
        ["updated_at"],
    )
    op.create_table(
        "agent_actions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(length=36),
            sa.ForeignKey("chat_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("action_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_agent_actions_conversation_created",
        "agent_actions",
        ["conversation_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_actions_conversation_created", table_name="agent_actions")
    op.drop_table("agent_actions")
    op.drop_index("ix_chat_conversations_updated_at", table_name="chat_conversations")
    op.drop_table("chat_conversations")
