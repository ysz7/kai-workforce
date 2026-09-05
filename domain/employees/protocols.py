from __future__ import annotations

from typing import Protocol

from domain.capabilities.models import CapabilityRequirement
from domain.employees.definition import EmployeeDefinition
from domain.tasks.task import Task, TaskResult
from domain.workspace.models import DEFAULT_WORKSPACE_ID, WorkspaceId


class Employee(Protocol):
    """One runtime serves every employee. The differences live in `definition`."""

    @property
    def definition(self) -> EmployeeDefinition: ...

    async def perform(self, assignment: object) -> TaskResult:
        """Execute an assignment.

        Typed as `object` to keep this module free of a cycle with
        `domain.workforce`; the runtime always receives a `TaskAssignment`.
        """
        ...


class EmployeeRegistry(Protocol):
    """The only way KAI learns who exists.

    Adding an employee is a new declaration and zero edits to KAI.
    """

    def list(self, workspace: WorkspaceId = DEFAULT_WORKSPACE_ID) -> list[EmployeeDefinition]: ...

    def get(self, name: str) -> EmployeeDefinition: ...

    def find_by_capability(
        self, requirement: CapabilityRequirement
    ) -> list[EmployeeDefinition]: ...


class Planner(Protocol):
    async def plan(self, task: Task) -> dict: ...


class Executor(Protocol):
    async def execute(self, task: Task) -> TaskResult: ...


class Verifier(Protocol):
    async def verify(self, task: Task, result: TaskResult) -> bool: ...
