"""One process, several watchers, no broker.

The platform is local-first: the run and the interface watching it are the same
process, so the whole of "real-time" here is an in-memory fan-out. No Redis, no
socket, nothing to install - and nothing to keep running when the interface is
closed.

Two properties are deliberate.

**Slow subscribers are dropped, never waited for.** A queue that blocks would
make a browser tab left open on a stalled connection able to stall the work it
is watching. Progress is expendable; the work is not.

**The buffer is short and per task.** It exists so a page opened one second
after a run started still shows the first line, not so the stream becomes a
second copy of the audit trail. What happened is answered by the task row and
the tool-call log, both of which outlive the process.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from domain.tasks.progress import ProgressEvent
from infrastructure.observability.logging import get_logger

log = get_logger(__name__)

#: How much of a run's recent progress a late subscriber is shown.
DEFAULT_BUFFER = 200
#: How far a single subscriber may fall behind before it stops being sent to.
DEFAULT_QUEUE = 100


class InMemoryProgressBroadcaster:
    """Implements `domain.tasks.progress.ProgressSink`, and hands out streams."""

    def __init__(self, *, buffer: int = DEFAULT_BUFFER, queue_size: int = DEFAULT_QUEUE) -> None:
        self._buffer_size = buffer
        self._queue_size = queue_size
        self._history: dict[UUID, deque[ProgressEvent]] = {}
        self._subscribers: set[asyncio.Queue[ProgressEvent]] = set()

    # --- Publishing -----------------------------------------------------------

    async def emit(self, event: ProgressEvent) -> None:
        history = self._history.setdefault(
            event.task_id, deque(maxlen=self._buffer_size)
        )
        history.append(event)
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # The watcher is not keeping up. Losing its next line is a far
                # better outcome than holding up the employee doing the work.
                log.debug("progress.subscriber_behind")

    # --- Watching -------------------------------------------------------------

    def recent(self, task_id: UUID) -> list[ProgressEvent]:
        """What this task has announced lately, oldest first."""
        return list(self._history.get(task_id, ()))

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[ProgressEvent]]:
        """A queue of everything announced from now on, cleaned up on exit."""
        queue: asyncio.Queue[ProgressEvent] = asyncio.Queue(maxsize=self._queue_size)
        self._subscribers.add(queue)
        try:
            yield queue
        finally:
            self._subscribers.discard(queue)

    async def stream(self, task_id: UUID | None = None) -> AsyncIterator[ProgressEvent]:
        """Every event, or every event of one task, as they arrive."""
        async with self.subscribe() as queue:
            while True:
                event = await queue.get()
                if task_id is None or event.task_id == task_id:
                    yield event

    def forget(self, task_id: UUID) -> None:
        self._history.pop(task_id, None)
