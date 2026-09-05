"""Approvals survive the process that asked the question."""

from __future__ import annotations

from uuid import uuid4

import pytest

from domain.approvals.models import Approval, ApprovalRequest, ApprovalState
from domain.policies.models import RiskLevel
from domain.tasks.task import Task
from infrastructure.persistence.approval_repository import (
    InMemoryApprovalRepository,
    SqliteApprovalRepository,
)
from infrastructure.persistence.task_repository import SqliteTaskRepository


@pytest.fixture
async def repository(request: pytest.FixtureRequest, sqlite_repository: SqliteTaskRepository):
    """SQLite only for the parts that need a real task row behind the foreign key."""
    return SqliteApprovalRepository(request.getfixturevalue("session_factory"))


async def stored_task(tasks: SqliteTaskRepository) -> Task:
    task = Task.create("Tidy the folder")
    await tasks.save(task)
    return task


def pending(task: Task, action: str = "fs.write(path='notes.txt')") -> Approval:
    return Approval(
        request=ApprovalRequest.create(
            task.id,
            action,
            payload={"path": "notes.txt"},
            risk_level=RiskLevel.HIGH,
            reason="Overwrite notes.txt",
        )
    )


async def test_a_question_survives_the_process_that_asked_it(
    repository, sqlite_repository
) -> None:
    task = await stored_task(sqlite_repository)
    approval = pending(task)

    await repository.save(approval)

    reloaded = await repository.get(approval.id)
    assert reloaded.state is ApprovalState.PENDING
    assert reloaded.request.risk_level is RiskLevel.HIGH
    assert reloaded.request.reason == "Overwrite notes.txt"
    assert reloaded.request.payload == {"path": "notes.txt"}


async def test_a_decision_replaces_the_pending_row(repository, sqlite_repository) -> None:
    task = await stored_task(sqlite_repository)
    approval = pending(task)
    await repository.save(approval)

    await repository.save(approval.resolve(ApprovalState.REJECTED, comment="not that file"))

    reloaded = await repository.get(approval.id)
    assert reloaded.state is ApprovalState.REJECTED
    assert reloaded.comment == "not that file"
    assert reloaded.resolved_at is not None
    assert await repository.list_pending() == []


async def test_pending_questions_are_listed_oldest_first(repository, sqlite_repository) -> None:
    task = await stored_task(sqlite_repository)
    for action in ("fs.write(a)", "fs.write(b)", "fs.write(c)"):
        await repository.save(pending(task, action))

    listed = await repository.list_pending()
    assert [a.request.action for a in listed] == ["fs.write(a)", "fs.write(b)", "fs.write(c)"]


async def test_an_unknown_approval_is_none(repository) -> None:
    assert await repository.get(uuid4()) is None


async def test_the_in_memory_repository_answers_the_same_way() -> None:
    memory = InMemoryApprovalRepository()
    approval = pending(Task.create("Tidy up"))

    await memory.save(approval)
    assert (await memory.list_pending())[0].id == approval.id

    await memory.save(approval.resolve(ApprovalState.APPROVED))
    assert await memory.list_pending() == []
