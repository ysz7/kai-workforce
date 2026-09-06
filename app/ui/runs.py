"""The tasks this process is carrying, and how to stop one.

The CLI runs a task and waits for it; an interface cannot. A request that starts
a task has to return the moment the task exists, because the point of the page
is to watch the run - so the work goes onto the event loop and the request
returns an id.

That leaves this file owning the two things a background run needs and a
foreground one does not.

**A task must exist before its request returns.** `submit` writes the task and
its assignment, and only then is the run scheduled. A page that got an id back
for a task the database has never heard of would be lying, and a process killed
one second later would have nothing to resume.

**Cancelling has two cases, and they are not the same.** A task this process is
running is asked to stop and stops itself between steps, keeping what it did. A
task that is *not* running - left behind by a killed process, or never started -
has nobody to ask, so it is moved to CANCELLED here. Conflating the two would
either leave a stale task uncancellable, or "cancel" a live run by writing a
terminal status underneath a loop that is still working.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

import structlog

from application.task_runner import TaskRunner
from domain.tasks.cancellation import Cancellations
from domain.tasks.repository import TaskRepository
from domain.tasks.task import Task, TaskResult, TaskStatus
from infrastructure.approvals.waiting import WaitingConfirmer

log = structlog.get_logger(__name__)

#: How long a shutdown waits for running tasks to stop themselves before they
#: are interrupted. Long enough for a step to finish, short enough that Ctrl-C
#: still feels like Ctrl-C.
SHUTDOWN_GRACE_SECONDS = 10.0


class Runs:
    """Starts tasks in the background and keeps track of the live ones."""

    def __init__(
        self,
        *,
        runner: TaskRunner,
        tasks: TaskRepository,
        cancellations: Cancellations,
        approvals: WaitingConfirmer,
    ) -> None:
        self._runner = runner
        self._tasks = tasks
        self._cancellations = cancellations
        self._approvals = approvals
        self._running: dict[UUID, asyncio.Task[Task]] = {}

    # --- Starting -------------------------------------------------------------

    async def start(self, goal: str, employee_name: str) -> Task:
        """Record the task, schedule the work, and hand the task straight back."""
        task, assignment = await self._runner.submit(goal, employee_name)
        run = asyncio.create_task(
            self._runner.run(task, assignment), name=f"kai-task-{task.id}"
        )
        self._running[task.id] = run
        run.add_done_callback(lambda _: self._finished(task.id))
        return task

    def _finished(self, task_id: UUID) -> None:
        self._running.pop(task_id, None)
        # A cancellation that outlived its run would silently stop the next one
        # started under the same id - which `resume` is entitled to do.
        self._cancellations.clear(task_id)

    def is_running(self, task_id: UUID) -> bool:
        return task_id in self._running

    @property
    def running(self) -> frozenset[UUID]:
        return frozenset(self._running)

    # --- Stopping -------------------------------------------------------------

    async def cancel(self, task_id: UUID, reason: str = "") -> Task | None:
        """Ask a task to stop. Returns the task, or None if there is no such task."""
        task = await self._tasks.get(task_id)
        if task is None:
            return None
        if task.is_terminal:
            return task

        if self.is_running(task_id):
            self._cancellations.cancel(task_id, reason)
            # A run parked on an approval is not between steps and would not see
            # the request until the question times out. Releasing it answers no,
            # which is the same answer the timeout would eventually give.
            released = self._approvals.release(task_id)
            log.info(
                "task.cancel_signalled",
                task_id=str(task_id),
                approvals_released=released,
            )
            return task

        cancelled, event = task.transition_to(
            TaskStatus.CANCELLED,
            result=task.result or TaskResult(summary=reason or "Cancelled before it ran."),
        )
        await self._tasks.save(cancelled, event)
        log.info("task.cancelled_while_idle", task_id=str(task_id), status=task.status.value)
        return cancelled

    async def aclose(self) -> None:
        """Stop carrying anything, without leaving a run half-written.

        Every live run is asked to stop the cooperative way first, so it writes
        its own terminal state; only a run that ignores that is cancelled
        outright, and a run interrupted that way is resumable by construction.
        """
        for task_id in list(self._running):
            self._cancellations.cancel(task_id, "The interface is shutting down.")
            self._approvals.release(task_id)
        pending = list(self._running.values())
        if not pending:
            return
        done, still_running = await asyncio.wait(pending, timeout=SHUTDOWN_GRACE_SECONDS)
        del done
        for run in still_running:
            run.cancel()
        await asyncio.gather(*still_running, return_exceptions=True)

    # --- Approvals ------------------------------------------------------------

    def decide(self, approval_id: UUID, approved: bool) -> bool:
        """Answer a question a tool call is parked on.

        False means no call in this process was waiting on it - a row left by an
        earlier run, which the caller records against instead.
        """
        return self._approvals.decide(approval_id, approved)
