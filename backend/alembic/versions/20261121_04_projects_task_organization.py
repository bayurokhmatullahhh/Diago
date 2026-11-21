"""Add projects and task organization fields.

Revision ID: 20261121_04
"""

from alembic import op
import sqlalchemy as sa

revision = "20261121_04"
down_revision = "20261121_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    with op.batch_alter_table("todos") as batch_op:
        batch_op.add_column(sa.Column("project_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("priority", sa.String(length=6), server_default="normal", nullable=False)
        )
        batch_op.create_foreign_key(
            "fk_todos_project_id_projects",
            "projects",
            ["project_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_todos_project_id", ["project_id"])
        batch_op.create_index("ix_todos_priority", ["priority"])


def downgrade() -> None:
    with op.batch_alter_table("todos") as batch_op:
        batch_op.drop_index("ix_todos_priority")
        batch_op.drop_index("ix_todos_project_id")
        batch_op.drop_constraint("fk_todos_project_id_projects", type_="foreignkey")
        batch_op.drop_column("priority")
        batch_op.drop_column("project_id")
    op.drop_table("projects")
