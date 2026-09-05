"""The declarations are the source of truth; the table is a loaded copy."""

from __future__ import annotations

from dataclasses import replace

from sqlalchemy import select

from infrastructure.persistence.employee_repository import SqliteEmployeeRepository
from infrastructure.persistence.models import EmployeeRow
from infrastructure.persistence.session import session_scope
from tests.fakes.employees import definition


async def rows(session_factory) -> list[EmployeeRow]:
    async with session_scope(session_factory) as session:
        return list(await session.scalars(select(EmployeeRow)))


async def test_declarations_are_written_in(session_factory) -> None:
    repository = SqliteEmployeeRepository(session_factory)
    changed = await repository.sync([definition("researcher"), definition("analyst")])

    assert changed == 2
    assert {row.name for row in await rows(session_factory)} == {"researcher", "analyst"}


async def test_syncing_again_changes_nothing(session_factory) -> None:
    repository = SqliteEmployeeRepository(session_factory)
    declared = [definition("researcher")]

    await repository.sync(declared)
    assert await repository.sync(declared) == 0


async def test_an_edited_declaration_is_written_back_under_the_same_id(
    session_factory,
) -> None:
    # The id is stable so that history keeps pointing at the right employee;
    # the hash is what makes the edit visible.
    repository = SqliteEmployeeRepository(session_factory)
    original = definition("researcher")
    await repository.sync([original])

    edited = replace(original, allowed_tools=frozenset({"fs.read"}))
    assert await repository.sync([edited]) == 1

    stored = (await rows(session_factory))[0]
    assert stored.id == str(original.id)
    assert stored.allowed_tools == ["fs.read"]
    assert stored.definition_hash == edited.definition_hash


async def test_the_stored_copy_carries_what_history_needs(session_factory) -> None:
    await SqliteEmployeeRepository(session_factory).sync([definition("researcher")])
    stored = (await rows(session_factory))[0]

    assert stored.role == "Research Specialist"
    assert stored.goals[0]["text"] == "Answer the question that was asked."
    assert stored.memory_scope == "EMPLOYEE_PRIVATE"
    assert stored.workspace_id == "default"
    assert stored.enabled is True
