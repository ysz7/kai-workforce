"""Persistence contract for tasks. No SQL ever crosses this boundary."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from domain.tasks.task import Task, TaskEvent
from domain.workspace.models import DEFAULT_WORKSPACE_ID, WorkspaceId


class TaskRepository(Protocol):
    async def save(self, task: Task, event: TaskEvent | None = None) -> None:
        """Persist the task and, when a transition produced one, its event."""
        ...

    async def get(self, task_id: UUID) -> Task | None: ...

    async def list_resumable(
        self, workspace_id: WorkspaceId = DEFAULT_WORKSPACE_ID
    ) -> list[Task]:
        """Tasks that can be picked up again after a restart."""
        ...

    async def events(self, task_id: UUID) -> list[TaskEvent]: ...
