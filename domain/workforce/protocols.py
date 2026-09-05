"""The manager's contract.

Declared in Phase 1 so everything below it is written against a fixed shape;
implemented in Phase 7, once there is a dependable executor to manage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID, uuid4

from domain.tasks.task import Task
from domain.workforce.assignment import TaskAssignment
from domain.workspace.models import DEFAULT_WORKSPACE_ID, WorkspaceId


class ObjectiveStatus(StrEnum):
    RECEIVED = "RECEIVED"
    PLANNING = "PLANNING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    ESCALATED = "ESCALATED"


@dataclass(frozen=True, slots=True)
class Objective:
    """What the user asked for, in their own words."""

    id: UUID
    text: str
    workspace_id: WorkspaceId = DEFAULT_WORKSPACE_ID
    constraints: dict[str, Any] = field(default_factory=dict)
    status: ObjectiveStatus = ObjectiveStatus.RECEIVED
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(cls, text: str, **extra: Any) -> Objective:
        return cls(id=uuid4(), text=text, **extra)


class PlanStatus(StrEnum):
    DRAFT = "DRAFT"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    SUPERSEDED = "SUPERSEDED"


@dataclass(frozen=True, slots=True)
class Plan:
    """A decomposition of one objective into tasks, plus their dependencies."""

    id: UUID
    objective_id: UUID
    tasks: tuple[Task, ...] = ()
    dependencies: tuple[tuple[UUID, UUID], ...] = ()  # (task_id, depends_on)
    revision: int = 1
    status: PlanStatus = PlanStatus.DRAFT
    rationale: str = ""
    workspace_id: WorkspaceId = DEFAULT_WORKSPACE_ID

    @classmethod
    def create(cls, objective_id: UUID, **extra: Any) -> Plan:
        return cls(id=uuid4(), objective_id=objective_id, **extra)


@dataclass(frozen=True, slots=True)
class PlanProgress:
    plan_id: UUID
    total: int
    completed: int
    failed: int
    running: int

    @property
    def is_finished(self) -> bool:
        return self.completed + self.failed == self.total


@dataclass(frozen=True, slots=True)
class ObjectiveResult:
    objective_id: UUID
    summary: str
    status: ObjectiveStatus
    output: dict[str, Any] = field(default_factory=dict)


class WorkforceManager(Protocol):
    """KAI's contract: the user's single entry point into the workforce."""

    async def handle_objective(self, objective: Objective) -> ObjectiveResult: ...

    async def plan(self, objective: Objective) -> Plan: ...

    async def delegate(self, task: Task) -> TaskAssignment: ...

    async def supervise(self, plan_id: UUID) -> PlanProgress: ...

    async def synthesize(self, plan_id: UUID) -> ObjectiveResult: ...


class Delegator(Protocol):
    """Picks the employee for a task and produces the assignment."""

    async def delegate(self, task: Task) -> TaskAssignment: ...
