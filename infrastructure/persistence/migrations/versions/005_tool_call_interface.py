"""Phase 5: which level of the interface hierarchy a tool call went through.

Revision ID: 005
Revises: 004
Create Date: 2026-09-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None

#: Existing rows were all made before any screen could be driven, so the
#: backfill is not a guess: every one of them was a direct call.
DEFAULT_INTERFACE = "API"


def upgrade() -> None:
    op.add_column(
        "tool_calls",
        sa.Column(
            "interface",
            sa.String(16),
            nullable=False,
            server_default=DEFAULT_INTERFACE,
        ),
    )


def downgrade() -> None:
    op.drop_column("tool_calls", "interface")
