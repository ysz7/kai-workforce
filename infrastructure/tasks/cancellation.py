"""Which tasks have been asked to stop, for as long as this process lives.

Deliberately not a file, and deliberately not a column. `kai stop` is a file
because it has to work from a second terminal while the first one holds the
screen. Cancelling a task is the opposite situation: the person asking is
already talking to the process that is running it, through the interface that
started it. A file would buy nothing and would then have to be cleaned up after
a crash, whereas a request that dies with the process is exactly right - a task
that was cancelled and then interrupted comes back through `resume` as the task
it was, and can be cancelled again.
"""

from __future__ import annotations

from uuid import UUID

from infrastructure.observability.logging import get_logger

log = get_logger(__name__)


class InMemoryCancellations:
    """Implements `domain.tasks.cancellation.Cancellations`."""

    def __init__(self) -> None:
        self._reasons: dict[UUID, str] = {}

    def cancel(self, task_id: UUID, reason: str = "") -> None:
        self._reasons[task_id] = reason
        log.info("task.cancel_requested", task_id=str(task_id), reason=reason)

    def is_cancelled(self, task_id: UUID) -> bool:
        return task_id in self._reasons

    def reason_for(self, task_id: UUID) -> str:
        return self._reasons.get(task_id, "")

    def clear(self, task_id: UUID) -> None:
        self._reasons.pop(task_id, None)
