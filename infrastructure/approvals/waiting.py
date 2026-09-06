"""An approval that waits for a click instead of a keystroke.

`console_confirmer` asks the person at the terminal and blocks until they type.
The local interface needs the same question answered by a different person in a
different place, so the wait moves into a future: the tool call parks, the
question appears in the browser, and the answer completes the future.

Three decisions carry the safety of this, all of them the same rule seen from
different sides - an unanswered question is not a yes.

**A wait has a deadline.** Without one, a run whose interface is closed holds a
tool call open forever, and the task can neither finish nor be resumed. When the
deadline passes the answer is no.

**A cancelled task releases its questions.** Otherwise `cancel` on a task parked
on an approval does nothing until the timeout, and the person is told the work
is stopping while it is not.

**Anything but an explicit approval is a rejection**, including a shutdown that
never delivered the answer at all.

The question is also announced on the progress stream as it is parked, because
a run that has stopped and does not say why looks identical to a run that has
hung.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import UUID

from domain.approvals.models import ApprovalRequest
from domain.tasks.progress import NullProgress, ProgressEvent, ProgressKind, ProgressSink
from infrastructure.observability.logging import get_logger

log = get_logger(__name__)

#: How long an irreversible action waits for a person before giving up. Long
#: enough to read the question and think; short enough that a forgotten browser
#: tab does not park a task for the rest of the day.
DEFAULT_TIMEOUT_SECONDS = 600.0


@dataclass(frozen=True, slots=True)
class WaitingApproval:
    """A question on screen, and the future the tool call is parked on."""

    request: ApprovalRequest
    answer: asyncio.Future[bool]


class WaitingConfirmer:
    """A `Confirmer` that is answered from somewhere other than this call stack."""

    def __init__(
        self,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        progress: ProgressSink | None = None,
    ) -> None:
        self._timeout = timeout_seconds
        self._progress = progress or NullProgress()
        self._waiting: dict[UUID, WaitingApproval] = {}

    async def __call__(self, request: ApprovalRequest) -> bool:
        loop = asyncio.get_running_loop()
        pending = WaitingApproval(request=request, answer=loop.create_future())
        self._waiting[request.id] = pending
        log.info(
            "approval.waiting",
            approval_id=str(request.id),
            task_id=str(request.task_id),
            action=request.action,
        )
        await self._announce(request)
        try:
            return await asyncio.wait_for(pending.answer, timeout=self._timeout)
        except TimeoutError:
            log.info("approval.timed_out", approval_id=str(request.id))
            return False
        except asyncio.CancelledError:
            # The run is going away. Nobody said yes, so the answer is no - and
            # the exception still propagates, because the caller is being torn
            # down and must not be resumed.
            raise
        finally:
            self._waiting.pop(request.id, None)

    async def _announce(self, request: ApprovalRequest) -> None:
        try:
            await self._progress.emit(
                ProgressEvent(
                    task_id=request.task_id,
                    kind=ProgressKind.APPROVAL,
                    message=request.action,
                    payload={
                        "approval_id": str(request.id),
                        "risk": request.risk_level.value,
                        "reason": request.reason,
                    },
                    workspace_id=request.workspace_id,
                )
            )
        except Exception as error:  # a watcher must not be able to fail a run
            log.warning("progress.emit_failed", kind=ProgressKind.APPROVAL.value, error=str(error))

    # --- The other side -------------------------------------------------------

    def pending(self, task_id: UUID | None = None) -> list[ApprovalRequest]:
        """The questions currently on screen, optionally for one task."""
        return [
            item.request
            for item in self._waiting.values()
            if task_id is None or item.request.task_id == task_id
        ]

    def decide(self, approval_id: UUID, approved: bool) -> bool:
        """Answer one question. False means it was not this process's to answer."""
        pending = self._waiting.get(approval_id)
        if pending is None or pending.answer.done():
            return False
        pending.answer.set_result(approved)
        return True

    def release(self, task_id: UUID) -> int:
        """Reject everything this task is waiting on, and say how many."""
        released = [item for item in self._waiting.values() if item.request.task_id == task_id]
        for item in released:
            if not item.answer.done():
                item.answer.set_result(False)
        return len(released)
