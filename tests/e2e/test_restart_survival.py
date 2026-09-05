"""Tasks survive a restart.

This is the Phase 1 property everything later depends on: the runtime saves the
step cursor after every step, so an interrupted run is picked up rather than
started over.
"""

from __future__ import annotations

from pathlib import Path

from domain.tasks.task import Task, TaskStatus
from infrastructure.persistence.models import Base
from infrastructure.persistence.session import create_engine, create_session_factory
from infrastructure.persistence.task_repository import SqliteTaskRepository


async def test_work_in_progress_is_recovered_from_a_new_process(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'kai.db'}"

    # --- First run: start a task, get two steps in, then "crash". -------------
    engine = create_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    repository = SqliteTaskRepository(create_session_factory(engine))

    task = Task.create("Compile the weekly report")
    await repository.save(task)
    running, event = task.transition_to(TaskStatus.RUNNING)
    await repository.save(running, event)
    running = running.with_execution(running.execution.advance(section="intro"))
    await repository.save(running)
    running = running.with_execution(running.execution.advance(section="numbers"))
    await repository.save(running)

    await engine.dispose()

    # --- Second run: a brand new engine, as after a restart. ------------------
    engine = create_engine(database_url)
    repository = SqliteTaskRepository(create_session_factory(engine))

    resumable = await repository.list_resumable()
    assert [t.id for t in resumable] == [task.id]

    recovered = resumable[0]
    assert recovered.status is TaskStatus.RUNNING
    assert recovered.execution.step == 2
    assert recovered.execution.state == {"section": "numbers"}
    assert recovered.goal == "Compile the weekly report"

    history = await repository.events(task.id)
    assert [(e.from_status, e.to_status) for e in history] == [
        (TaskStatus.CREATED, TaskStatus.RUNNING)
    ]

    await engine.dispose()
