"""Persistence contract for assignments: who was asked to do what, by whom."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from domain.employees.definition import EmployeeId
from domain.workforce.assignment import TaskAssignment


class AssignmentRepository(Protocol):
    async def save(self, assignment: TaskAssignment) -> None: ...

    async def get(self, assignment_id: UUID) -> TaskAssignment | None: ...

    async def for_task(self, task_id: UUID) -> list[TaskAssignment]:
        """Every assignment made for a task, newest first.

        A task can be assigned more than once - reassigned after a failure, or
        retried - and the history is what makes that legible afterwards.
        """
        ...

    async def for_employee(self, employee_id: EmployeeId) -> list[TaskAssignment]: ...
