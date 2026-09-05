"""Starts tasks, resumes them, and retries the failures worth retrying.

This is the entry point every interface uses - the CLI today, the local UI in
Phase 6, KAI in Phase 7 - so that "run a task" means the same thing regardless
of who asked.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import replace

import structlog

from application.employee_runtime.runtime import EmployeeRuntime
from application.orchestrator import Failure, classify
from domain.employees.definition import EmployeeDefinition
from domain.employees.protocols import EmployeeRegistry
from domain.policies.models import ActorKind
from domain.tasks.repository import TaskRepository
from domain.tasks.task import Task, TaskCreatedBy, TaskError, TaskResult, TaskStatus
from domain.workforce.assignment import AssignmentOutcome, SharedContext, TaskAssignment
from domain.workforce.repository import AssignmentRepository
from domain.workspace.models import DEFAULT_WORKSPACE_ID, WorkspaceId

log = structlog.get_logger(__name__)

#: How many times a transient failure is worth re-entering the task for. The
#: provider adapter already retries individual calls; this covers a failure that
#: killed the whole run.
MAX_TASK_ATTEMPTS = 2


class TaskRunner:
    def __init__(
        self,
        *,
        tasks: TaskRepository,
        assignments: AssignmentRepository,
        registry: EmployeeRegistry,
        build_runtime: Callable[[EmployeeDefinition], Awaitable[EmployeeRuntime]],
        max_attempts: int = MAX_TASK_ATTEMPTS,
    ) -> None:
        self._tasks = tasks
        self._assignments = assignments
        self._registry = registry
        self._build_runtime = build_runtime
        self._max_attempts = max_attempts

    # --- Starting -------------------------------------------------------------

    async def submit(
        self,
        goal: str,
        employee_name: str,
        *,
        created_by: TaskCreatedBy = TaskCreatedBy.USER,
        assigned_by: ActorKind = ActorKind.USER,
        context: SharedContext | None = None,
        workspace_id: WorkspaceId = DEFAULT_WORKSPACE_ID,
    ) -> tuple[Task, TaskAssignment]:
        """Record the task and who it went to, before any work starts.

        Written down first so that a process killed one second later still has a
        task to come back to.
        """
        definition = self._registry.get(employee_name)
        task = replace(
            Task.create(goal, workspace_id=workspace_id, created_by=created_by),
            assigned_employee_id=definition.id,
        )
        await self._tasks.save(task)

        assignment = TaskAssignment.create(
            task_id=task.id,
            employee_id=definition.id,
            assigned_by=assigned_by,
            context=context or SharedContext(),
            workspace_id=workspace_id,
        ).accept()
        await self._assignments.save(assignment)
        log.info(
            "task.submitted",
            task_id=str(task.id),
            employee=definition.name,
            assigned_by=assigned_by.value,
        )
        return task, assignment

    async def run(self, task: Task, assignment: TaskAssignment | None = None) -> Task:
        """Carry one task to a terminal state, retrying transient failures."""
        attempt = 1

        while True:
            try:
                # Assembling the runtime is inside the try on purpose: a missing
                # employee or an unconfigured provider fails here, and that is a
                # failure of the task like any other, not an escaping exception.
                definition = self._definition_for(task)
                runtime = await self._build_runtime(definition)
                await runtime.run(task, assignment)
                break
            except Exception as error:
                failure = classify(error)
                log.warning(
                    "task.failed",
                    task_id=str(task.id),
                    kind=failure.kind.value,
                    error_type=failure.error_type,
                    attempt=attempt,
                )
                if failure.is_retryable and attempt < self._max_attempts:
                    attempt += 1
                    task = await self._reload(task)
                    await asyncio.sleep(0)
                    continue
                task = await self._mark_failed(task, failure)
                break

        final = await self._reload(task)
        if assignment is not None:
            await self._close(assignment, final)
        return final

    async def submit_and_run(
        self, goal: str, employee_name: str, **kwargs: object
    ) -> Task:
        task, assignment = await self.submit(goal, employee_name, **kwargs)  # type: ignore[arg-type]
        return await self.run(task, assignment)

    # --- Resuming -------------------------------------------------------------

    async def resumable(self, workspace_id: WorkspaceId = DEFAULT_WORKSPACE_ID) -> list[Task]:
        return await self._tasks.list_resumable(workspace_id)

    async def resume(self, task: Task) -> Task:
        """Pick a task up where it stopped.

        The runtime reads its own stage and transcript out of `task.execution`,
        so resuming is the same call as starting - the difference is entirely in
        the state that was saved.
        """
        assignments = await self._assignments.for_task(task.id)
        log.info(
            "task.resuming",
            task_id=str(task.id),
            status=task.status.value,
            step=task.execution.step,
        )
        return await self.run(task, assignments[0] if assignments else None)

    async def resume_all(
        self, workspace_id: WorkspaceId = DEFAULT_WORKSPACE_ID
    ) -> list[Task]:
        return [await self.resume(task) for task in await self.resumable(workspace_id)]

    # --- Internals ------------------------------------------------------------

    def _definition_for(self, task: Task) -> EmployeeDefinition:
        for definition in self._registry.list(task.workspace_id):
            if definition.id == task.assigned_employee_id:
                return definition
        from domain.errors import EmployeeNotFoundError

        raise EmployeeNotFoundError(str(task.assigned_employee_id))

    async def _reload(self, task: Task) -> Task:
        return await self._tasks.get(task.id) or task

    async def _mark_failed(self, task: Task, failure: Failure) -> Task:
        current = await self._reload(task)
        if current.is_terminal:
            return current
        failed, event = current.transition_to(
            TaskStatus.FAILED,
            error=TaskError(
                kind=failure.error_type, message=failure.message, details={"kind": failure.kind}
            ),
            attempts=current.attempts + 1,
        )
        await self._tasks.save(failed, event)
        return failed

    async def _close(self, assignment: TaskAssignment, task: Task) -> None:
        outcome = (
            AssignmentOutcome.COMPLETED
            if task.status is TaskStatus.COMPLETED
            else AssignmentOutcome.FAILED
        )
        await self._assignments.save(
            assignment.close(outcome, task.result or TaskResult(summary=""))
        )
