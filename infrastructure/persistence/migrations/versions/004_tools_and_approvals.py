"""Phase 4: tool_calls and approvals.

Revision ID: 004
Revises: 003
Create Date: 2026-09-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None

APPROVAL_STATES = ("PENDING", "APPROVED", "REJECTED", "EXPIRED")


def upgrade() -> None:
    op.create_table(
        "tool_calls",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.String(36), nullable=True),
        sa.Column("tool", sa.String(64), nullable=False),
        sa.Column("input", sa.JSON(), nullable=True),
        sa.Column("output", sa.JSON(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_tool_calls_task_id", "tool_calls", ["task_id", "id"])

    op.create_table(
        "approvals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(64), nullable=False, server_default="default"),
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column("requested_by_employee_id", sa.String(36), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("risk_level", sa.String(16), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("requested_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_by", sa.String(64), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "state IN ('" + "','".join(APPROVAL_STATES) + "')", name="ck_approvals_state"
        ),
        sa.ForeignKeyConstraint(
            ["task_id"], ["tasks.id"], name="fk_approvals_task_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_employee_id"], ["employees.id"], name="fk_approvals_employee_id"
        ),
    )
    op.create_index("ix_approvals_state", "approvals", ["state", "requested_at"])


def downgrade() -> None:
    op.drop_index("ix_approvals_state", table_name="approvals")
    op.drop_table("approvals")
    op.drop_index("ix_tool_calls_task_id", table_name="tool_calls")
    op.drop_table("tool_calls")
