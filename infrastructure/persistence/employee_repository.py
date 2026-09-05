"""Keeps the `employees` table in step with the declarations on disk.

The YAML files are the source of truth; this table is a loaded copy. It exists
so that a task, an assignment or an audit record can point at an employee by a
stable id, and so that a run from six months ago can still say who did it even
if the declaration has changed since.

`definition_hash` is what makes that detectable: a changed declaration writes a
new hash, and history keeps the id it always had.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from domain.employees.definition import EmployeeDefinition
from domain.errors import StorageError, StorageNotInitializedError
from infrastructure.observability.logging import get_logger
from infrastructure.persistence.models import EmployeeRow
from infrastructure.persistence.session import session_scope

log = get_logger(__name__)


def _to_values(definition: EmployeeDefinition) -> dict:
    return {
        "id": str(definition.id),
        "workspace_id": str(definition.workspace_id),
        "name": definition.name,
        "role": definition.role.title,
        "role_description": definition.role.description,
        "goals": [{"text": g.text, "priority": g.priority} for g in definition.goals],
        "policies": sorted(definition.policies),
        "allowed_tools": sorted(definition.allowed_tools),
        "model_profile": {
            "capabilities": sorted(str(c) for c in definition.model_profile.capabilities),
            "min_context_tokens": definition.model_profile.min_context_tokens,
            "temperature": definition.model_profile.temperature,
        },
        "memory_scope": str(definition.memory_scope),
        "enabled": definition.enabled,
        "definition_hash": definition.definition_hash,
    }


class SqliteEmployeeRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[AsyncSession]:
        try:
            async with session_scope(self._session_factory) as session:
                yield session
        except OperationalError as error:
            message = str(error.orig)
            if "no such table" in message or "unable to open database file" in message:
                raise StorageNotInitializedError("The local database has no schema yet.") from error
            raise StorageError(message) from error

    async def sync(self, definitions: list[EmployeeDefinition]) -> int:
        """Write the declarations in, and report how many actually changed."""
        changed = 0
        async with self._session() as session:
            existing = {
                row.id: row.definition_hash
                for row in await session.scalars(select(EmployeeRow))
            }
            for definition in definitions:
                values = _to_values(definition)
                if existing.get(values["id"]) == values["definition_hash"]:
                    continue
                changed += 1
                statement = sqlite_insert(EmployeeRow).values(**values)
                await session.execute(
                    statement.on_conflict_do_update(
                        index_elements=[EmployeeRow.id],
                        set_={k: v for k, v in values.items() if k != "id"},
                    )
                )
        if changed:
            log.info("employees.synced", changed=changed, total=len(definitions))
        return changed


class InMemoryEmployeeRepository:
    def __init__(self) -> None:
        self.definitions: dict[str, EmployeeDefinition] = {}

    async def sync(self, definitions: list[EmployeeDefinition]) -> int:
        changed = sum(
            1
            for d in definitions
            if self.definitions.get(str(d.id)) is None
            or self.definitions[str(d.id)].definition_hash != d.definition_hash
        )
        self.definitions = {str(d.id): d for d in definitions}
        return changed
