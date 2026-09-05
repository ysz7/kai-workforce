"""The same contract, checked in memory and on SQLite."""

from __future__ import annotations

from uuid import uuid4

import pytest

from domain.policies.models import ActorKind
from domain.tasks.task import Task, TaskResult
from domain.workforce.assignment import AssignmentOutcome, SharedContext, TaskAssignment
from infrastructure.persistence.assignment_repository import (
    InMemoryAssignmentRepository,
    SqliteAssignmentRepository,
)
from infrastructure.persistence.employee_repository import SqliteEmployeeRepository
from tests.fakes.employees import definition

EMPLOYEE = definition()


@pytest.fixture
async def repository(request: pytest.FixtureRequest, session_factory):
    if request.param == "in_memory":
        return InMemoryAssignmentRepository()
    # SQLite enforces the foreign keys, so the employee has to exist first.
    await SqliteEmployeeRepository(session_factory).sync([EMPLOYEE])
    return SqliteAssignmentRepository(session_factory)


@pytest.fixture
async def task(request: pytest.FixtureRequest, session_factory) -> Task:
    from dataclasses import replace

    from infrastructure.persistence.task_repository import SqliteTaskRepository

    created = replace(Task.create("Explain WAL mode"), assigned_employee_id=EMPLOYEE.id)
    if request.param != "in_memory":
        await SqliteTaskRepository(session_factory).save(created)
    return created


pytestmark = pytest.mark.parametrize(
    ("repository", "task"), [("in_memory", "in_memory"), ("sqlite", "sqlite")], indirect=True
)


async def test_an_assignment_round_trips(repository, task) -> None:
    assignment = TaskAssignment.create(
        task_id=task.id,
        employee_id=EMPLOYEE.id,
        assigned_by=ActorKind.USER,
        context=SharedContext(facts=("deadline is Friday",), data={"budget": 3}),
    )
    await repository.save(assignment)

    stored = await repository.get(assignment.id)
    assert stored.task_id == task.id
    assert stored.assigned_by is ActorKind.USER
    assert stored.context.facts == ("deadline is Friday",)
    assert stored.context.data == {"budget": 3}
    assert stored.outcome is None


async def test_closing_an_assignment_records_the_result(repository, task) -> None:
    assignment = TaskAssignment.create(
        task_id=task.id, employee_id=EMPLOYEE.id, assigned_by=ActorKind.KAI
    )
    await repository.save(assignment)
    await repository.save(
        assignment.close(AssignmentOutcome.COMPLETED, TaskResult(summary="done", output={"n": 1}))
    )

    stored = await repository.get(assignment.id)
    assert stored.outcome is AssignmentOutcome.COMPLETED
    assert stored.completed_at is not None
    assert stored.result.output == {"n": 1}


async def test_a_tasks_assignments_come_back_newest_first(repository, task) -> None:
    # A task can be assigned more than once - reassigned, or retried - and the
    # history is what makes that legible afterwards.
    from dataclasses import replace
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    first = replace(
        TaskAssignment.create(task.id, EMPLOYEE.id, ActorKind.USER),
        assigned_at=now - timedelta(hours=1),
    )
    second = TaskAssignment.create(task.id, EMPLOYEE.id, ActorKind.KAI)
    await repository.save(first)
    await repository.save(second)

    history = await repository.for_task(task.id)
    assert [a.id for a in history] == [second.id, first.id]


async def test_assignments_can_be_read_per_employee(repository, task) -> None:
    assignment = TaskAssignment.create(task.id, EMPLOYEE.id, ActorKind.USER)
    await repository.save(assignment)

    assert [a.id for a in await repository.for_employee(EMPLOYEE.id)] == [assignment.id]
    assert await repository.for_employee(uuid4()) == []


async def test_a_missing_assignment_is_none(repository, task) -> None:
    assert await repository.get(uuid4()) is None
