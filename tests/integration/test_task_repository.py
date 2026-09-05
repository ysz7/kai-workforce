"""The same contract, checked against both implementations.

If a test passes in memory and fails on SQLite, the repository is leaking
storage behaviour into the domain.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from domain.tasks.task import Task, TaskResult, TaskStatus
from infrastructure.persistence.in_memory_task_repository import InMemoryTaskRepository


@pytest.fixture(params=["in_memory", "sqlite"])
def repository(request: pytest.FixtureRequest):
    if request.param == "in_memory":
        return InMemoryTaskRepository()
    return request.getfixturevalue("sqlite_repository")


async def test_saved_task_round_trips(repository) -> None:
    task = Task.create("Draft the release notes")
    await repository.save(task)

    loaded = await repository.get(task.id)
    assert loaded is not None
    assert loaded.id == task.id
    assert loaded.goal == task.goal
    assert loaded.status is TaskStatus.CREATED
    assert loaded.workspace_id == task.workspace_id


async def test_missing_task_is_none(repository) -> None:
    assert await repository.get(uuid4()) is None


async def test_execution_state_survives_a_reload(repository) -> None:
    task = Task.create("Collect the quarterly numbers")
    await repository.save(task)

    running, event = task.transition_to(TaskStatus.RUNNING)
    running = running.with_execution(running.execution.advance(cursor="page-2"))
    await repository.save(running, event)

    loaded = await repository.get(task.id)
    assert loaded is not None
    assert loaded.status is TaskStatus.RUNNING
    assert loaded.execution.step == 1
    assert loaded.execution.state == {"cursor": "page-2"}


async def test_only_unfinished_work_is_resumable(repository) -> None:
    running = Task.create("Keep going")
    running, event = running.transition_to(TaskStatus.RUNNING)
    await repository.save(running, event)

    done = Task.create("Already handled")
    done, event = done.transition_to(TaskStatus.RUNNING)
    await repository.save(done, event)
    done, event = done.complete(TaskResult(summary="handled"))
    await repository.save(done, event)

    resumable = await repository.list_resumable()
    assert [task.id for task in resumable] == [running.id]


async def test_transitions_are_recorded_in_order(repository) -> None:
    task = Task.create("Trace me")
    await repository.save(task)

    running, event = task.transition_to(TaskStatus.RUNNING)
    await repository.save(running, event)
    verifying, event = running.transition_to(TaskStatus.VERIFYING)
    await repository.save(verifying, event)

    events = await repository.events(task.id)
    assert [(e.from_status, e.to_status) for e in events] == [
        (TaskStatus.CREATED, TaskStatus.RUNNING),
        (TaskStatus.RUNNING, TaskStatus.VERIFYING),
    ]


async def test_result_and_error_payloads_round_trip(repository) -> None:
    task = Task.create("Produce something")
    running, event = task.transition_to(TaskStatus.RUNNING)
    await repository.save(running, event)

    completed, event = running.complete(
        TaskResult(summary="done", output={"count": 3}, artifacts=("report.md",))
    )
    await repository.save(completed, event)

    loaded = await repository.get(task.id)
    assert loaded is not None
    assert loaded.result is not None
    assert loaded.result.output == {"count": 3}
    assert loaded.result.artifacts == ("report.md",)
