"""SQLAlchemy models, written natively for SQLite.

UUIDs and timestamps are TEXT, JSON is TEXT read through SQLite's JSON
functions, and enums are TEXT with a CHECK constraint. Portability is provided
by the Protocols in `domain/`, not by a dialect-agnostic subset of SQL.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON

from domain.tasks.task import TaskStatus

TASK_STATUS_VALUES = tuple(status.value for status in TaskStatus)


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(UTC)


class EmployeeRow(Base):
    """The loaded version of an employee declaration.

    The source of truth stays the file under `employees/`; this table holds what
    was loaded plus any local override.
    """

    __tablename__ = "employees"
    __table_args__ = (UniqueConstraint("workspace_id", "name", name="uq_employees_workspace_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(256), nullable=False)
    role_description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    goals: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    policies: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    allowed_tools: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    model_profile: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    memory_scope: Mapped[str] = mapped_column(
        String(32), nullable=False, default="EMPLOYEE_PRIVATE"
    )
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    definition_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)


class TaskRow(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('" + "','".join(TASK_STATUS_VALUES) + "')",
            name="ck_tasks_status",
        ),
        Index("ix_tasks_workspace_status", "workspace_id", "status", "priority", "created_at"),
        Index("ix_tasks_parent_id", "parent_id"),
        Index("ix_tasks_plan_id", "plan_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    created_by: Mapped[str] = mapped_column(String(32), nullable=False, default="user")
    parent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True
    )
    # No FK yet: plans arrive in Phase 7.
    plan_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    workflow_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=TaskStatus.CREATED.value
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    assigned_employee_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("employees.id"), nullable=True
    )
    plan: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    #: Step cursor and scratch state, saved after every step so a task survives
    #: a restart.
    state: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)


class TaskEventRow(Base):
    __tablename__ = "task_events"
    __table_args__ = (Index("ix_task_events_task_id", "task_id", "id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)
