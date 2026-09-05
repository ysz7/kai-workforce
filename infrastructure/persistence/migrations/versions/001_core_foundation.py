"""Phase 1: employees, tasks, task_events.

Revision ID: 001
Revises:
Create Date: 2026-09-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None

TASK_STATUSES = (
    "CREATED",
    "PLANNING",
    "RUNNING",
    "WAITING_FOR_TOOL",
    "WAITING_FOR_APPROVAL",
    "VERIFYING",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
)


def upgrade() -> None:
    op.create_table(
        "employees",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(64), nullable=False, server_default="default"),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("role", sa.String(256), nullable=False),
        sa.Column("role_description", sa.Text(), nullable=False, server_default=""),
        sa.Column("goals", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("policies", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("allowed_tools", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("model_profile", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "memory_scope", sa.String(32), nullable=False, server_default="EMPLOYEE_PRIVATE"
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("definition_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("workspace_id", "name", name="uq_employees_workspace_name"),
    )

    op.create_table(
        "tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(64), nullable=False, server_default="default"),
        sa.Column("created_by", sa.String(32), nullable=False, server_default="user"),
        sa.Column("parent_id", sa.String(36), nullable=True),
        sa.Column("plan_id", sa.String(36), nullable=True),
        sa.Column("workflow_run_id", sa.String(36), nullable=True),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="CREATED"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("assigned_employee_id", sa.String(36), nullable=True),
        sa.Column("plan", sa.JSON(), nullable=True),
        sa.Column("state", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.JSON(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["parent_id"], ["tasks.id"], name="fk_tasks_parent_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["assigned_employee_id"], ["employees.id"], name="fk_tasks_employee_id"
        ),
        sa.CheckConstraint(
            "status IN ('" + "','".join(TASK_STATUSES) + "')", name="ck_tasks_status"
        ),
    )
    op.create_index(
        "ix_tasks_workspace_status", "tasks", ["workspace_id", "status", "priority", "created_at"]
    )
    op.create_index("ix_tasks_parent_id", "tasks", ["parent_id"])
    op.create_index("ix_tasks_plan_id", "tasks", ["plan_id"])

    op.create_table(
        "task_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column("from_status", sa.String(32), nullable=True),
        sa.Column("to_status", sa.String(32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id"], ["tasks.id"], name="fk_task_events_task_id", ondelete="CASCADE"
        ),
    )
    op.create_index("ix_task_events_task_id", "task_events", ["task_id", "id"])


def downgrade() -> None:
    op.drop_table("task_events")
    op.drop_index("ix_tasks_plan_id", table_name="tasks")
    op.drop_index("ix_tasks_parent_id", table_name="tasks")
    op.drop_index("ix_tasks_workspace_status", table_name="tasks")
    op.drop_table("tasks")
    op.drop_table("employees")
