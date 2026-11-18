"""Add persistent reminder scheduling and in-app notifications.

Revision ID: 20261110_01
"""

from alembic import op
import sqlalchemy as sa

revision = "20261110_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "todos" not in tables:
        op.create_table(
            "todos",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("status", sa.String(length=9), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_todos_status", "todos", ["status"])

    columns = {column["name"] for column in sa.inspect(bind).get_columns("todos")}
    if "reminder_at" not in columns:
        op.add_column(
            "todos", sa.Column("reminder_at", sa.DateTime(timezone=True), nullable=True)
        )
    if "reminder_revision" not in columns:
        op.add_column(
            "todos",
            sa.Column(
                "reminder_revision",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )
    if "reminder_sent_at" not in columns:
        op.add_column(
            "todos", sa.Column("reminder_sent_at", sa.DateTime(timezone=True), nullable=True)
        )

    if "ix_todos_reminder_at" not in {
        index["name"] for index in sa.inspect(bind).get_indexes("todos")
    }:
        op.create_index("ix_todos_reminder_at", "todos", ["reminder_at"])

    if "notifications" not in tables:
        op.create_table(
            "notifications",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "todo_id",
                sa.Integer(),
                sa.ForeignKey("todos.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("todo_title", sa.String(length=200), nullable=False),
            sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("reminder_revision", sa.Integer(), nullable=False),
            sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.UniqueConstraint(
                "todo_id", "reminder_revision", name="uq_notification_todo_revision"
            ),
        )
        op.create_index("ix_notifications_todo_id", "notifications", ["todo_id"])
        op.create_index("ix_notifications_is_read", "notifications", ["is_read"])


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "notifications" in tables:
        op.drop_table("notifications")
    if "todos" in tables:
        indexes = {index["name"] for index in sa.inspect(bind).get_indexes("todos")}
        if "ix_todos_reminder_at" in indexes:
            op.drop_index("ix_todos_reminder_at", table_name="todos")
        columns = {column["name"] for column in sa.inspect(bind).get_columns("todos")}
        with op.batch_alter_table("todos") as batch:
            for name in ("reminder_sent_at", "reminder_revision", "reminder_at"):
                if name in columns:
                    batch.drop_column(name)
