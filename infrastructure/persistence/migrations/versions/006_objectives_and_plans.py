"""Phase 7: objectives and plans - what the user asked KAI for, and its decomposition.

Revision ID: 006
Revises: 005
Create Date: 2026-09-06

Two notes on foreign keys, both about the same thing: a plan is written before
the work in it exists.

`tasks.plan_id` gets no key. The target schema adds one here, and SQLite cannot
add a constraint to an existing table - it means rebuilding `tasks`, which four
other tables reference and which holds the resume state of every interrupted
run. That is not worth doing for a column that has existed, indexed, since
migration 001.

`plan_task_dependencies` gets one key, to `plans`, and none to `tasks`. This is
not a workaround; it is what a plan is. KAI decomposes an objective into tasks
and records which of them wait for which *before* any of them runs, and a task
becomes a row when somebody is given it. Keying the edges to `tasks` would mean
a plan could only be recorded after it had already been carried out, which is
the opposite of what a plan is for. (Found the direct way: the first plan with
two tasks in it failed on exactly that key.)
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None

OBJECTIVE_STATUSES = ("RECEIVED", "PLANNING", "RUNNING", "DONE", "FAILED", "ESCALATED")
PLAN_STATUSES = ("DRAFT", "RUNNING", "DONE", "FAILED", "SUPERSEDED")


def upgrade() -> None:
    op.create_table(
        "objectives",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(64), nullable=False, server_default="default"),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("constraints", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("acceptance_criteria", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('" + "','".join(OBJECTIVE_STATUSES) + "')",
            name="ck_objectives_status",
        ),
    )
    op.create_index(
        "ix_objectives_workspace_created", "objectives", ["workspace_id", "created_at"]
    )

    op.create_table(
        "plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(64), nullable=False, server_default="default"),
        sa.Column("objective_id", sa.String(36), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('" + "','".join(PLAN_STATUSES) + "')", name="ck_plans_status"
        ),
        sa.ForeignKeyConstraint(
            ["objective_id"],
            ["objectives.id"],
            name="fk_plans_objective_id",
            ondelete="CASCADE",
        ),
        # A revision number that repeats would make "which plan came second"
        # unanswerable, which is the whole reason superseded plans are kept.
        sa.UniqueConstraint("objective_id", "revision", name="uq_plans_objective_revision"),
    )
    op.create_index("ix_plans_objective", "plans", ["objective_id", "revision"])

    op.create_table(
        "plan_task_dependencies",
        sa.Column("plan_id", sa.String(36), primary_key=True),
        sa.Column("task_id", sa.String(36), primary_key=True),
        sa.Column("depends_on", sa.String(36), primary_key=True),
        sa.ForeignKeyConstraint(
            ["plan_id"], ["plans.id"], name="fk_plan_deps_plan_id", ondelete="CASCADE"
        ),
    )


def downgrade() -> None:
    op.drop_table("plan_task_dependencies")
    op.drop_index("ix_plans_objective", table_name="plans")
    op.drop_table("plans")
    op.drop_index("ix_objectives_workspace_created", table_name="objectives")
    op.drop_table("objectives")
