"""Progress reaches everyone watching, and nobody watching can hold up the work."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from domain.tasks.progress import NullProgress, ProgressEvent, ProgressKind
from infrastructure.progress.broadcaster import InMemoryProgressBroadcaster


def _event(task_id, message: str = "working") -> ProgressEvent:
    return ProgressEvent(task_id=task_id, kind=ProgressKind.STAGE, message=message)


async def test_every_subscriber_gets_every_event() -> None:
    broadcaster = InMemoryProgressBroadcaster()
    task_id = uuid4()

    async with broadcaster.subscribe() as first, broadcaster.subscribe() as second:
        await broadcaster.emit(_event(task_id))
        assert (await first.get()).message == "working"
        assert (await second.get()).message == "working"


async def test_a_late_subscriber_can_replay_what_the_task_already_said() -> None:
    broadcaster = InMemoryProgressBroadcaster()
    task_id = uuid4()

    await broadcaster.emit(_event(task_id, "planning"))
    await broadcaster.emit(_event(task_id, "step one"))

    assert [e.message for e in broadcaster.recent(task_id)] == ["planning", "step one"]
    assert broadcaster.recent(uuid4()) == []


async def test_the_buffer_is_bounded_so_a_long_run_does_not_grow_forever() -> None:
    broadcaster = InMemoryProgressBroadcaster(buffer=3)
    task_id = uuid4()

    for index in range(10):
        await broadcaster.emit(_event(task_id, str(index)))

    assert [e.message for e in broadcaster.recent(task_id)] == ["7", "8", "9"]


async def test_a_subscriber_that_stops_reading_is_dropped_not_waited_for() -> None:
    """The property the work depends on: a stalled watcher cannot stall a run."""
    broadcaster = InMemoryProgressBroadcaster(queue_size=2)
    task_id = uuid4()

    async with broadcaster.subscribe() as queue:
        for index in range(20):
            # Would block forever on a queue with no room, if emit waited.
            await asyncio.wait_for(broadcaster.emit(_event(task_id, str(index))), timeout=1)
        assert queue.qsize() == 2


async def test_a_stream_can_be_narrowed_to_one_task() -> None:
    broadcaster = InMemoryProgressBroadcaster()
    watched, other = uuid4(), uuid4()
    seen: list[str] = []

    async def watch() -> None:
        async for event in broadcaster.stream(watched):
            seen.append(event.message)
            if len(seen) == 2:
                return

    watcher = asyncio.create_task(watch())
    await asyncio.sleep(0)  # let the subscription register before anything is sent
    await broadcaster.emit(_event(other, "not mine"))
    await broadcaster.emit(_event(watched, "mine"))
    await broadcaster.emit(_event(watched, "also mine"))
    await asyncio.wait_for(watcher, timeout=1)

    assert seen == ["mine", "also mine"]


async def test_the_null_sink_accepts_everything_and_keeps_nothing() -> None:
    """A run nobody is watching must cost nothing to be watchable."""
    sink = NullProgress()
    assert await sink.emit(_event(uuid4())) is None


async def test_a_finished_task_can_be_forgotten() -> None:
    broadcaster = InMemoryProgressBroadcaster()
    task_id = uuid4()
    await broadcaster.emit(_event(task_id))
    broadcaster.forget(task_id)
    assert broadcaster.recent(task_id) == []
