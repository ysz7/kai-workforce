"""Phase 3: task_assignments.

Revision ID: 003
Revises: 002
Create Date: 2026-09-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_assignments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(64), nullable=False, server_default="default"),
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column("employee_id", sa.String(36), nullable=False),
        sa.Column("assigned_by", sa.String(32), nullable=False),
        sa.Column("assigned_by_id", sa.String(64), nullable=True),
        sa.Column("context", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("assigned_at", sa.DateTime(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("outcome", sa.String(32), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["task_id"], ["tasks.id"], name="fk_assignments_task_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["employees.id"], name="fk_assignments_employee_id"
        ),
    )
    op.create_index(
        "ix_task_assignments_task", "task_assignments", ["task_id", "assigned_at"]
    )
    op.create_index(
        "ix_task_assignments_employee", "task_assignments", ["employee_id", "assigned_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_task_assignments_employee", table_name="task_assignments")
    op.drop_index("ix_task_assignments_task", table_name="task_assignments")
    op.drop_table("task_assignments")
