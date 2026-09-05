"""Tool-call telemetry storage. SQL does not leave this package."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from domain.errors import StorageError, StorageNotInitializedError
from domain.tools.telemetry import ToolCallRecord
from infrastructure.persistence.models import ToolCallRow
from infrastructure.persistence.session import session_scope


def _to_record(row: ToolCallRow) -> ToolCallRecord:
    created = row.created_at
    return ToolCallRecord(
        tool=row.tool,
        success=row.success,
        latency_ms=row.latency_ms,
        task_id=UUID(row.task_id) if row.task_id else None,
        input_data=row.input or {},
        output=row.output or {},
        error=row.error,
        created_at=created if created.tzinfo else created.replace(tzinfo=UTC),
    )


class SqliteToolCallLog:
    """Implements `domain.tools.telemetry.ToolCallLog`."""

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

    async def record(self, call: ToolCallRecord) -> None:
        safe = call.redacted()
        async with self._session() as session:
            session.add(
                ToolCallRow(
                    task_id=str(safe.task_id) if safe.task_id else None,
                    tool=safe.tool,
                    input=safe.input_data,
                    output=safe.output,
                    success=safe.success,
                    error=safe.error,
                    latency_ms=safe.latency_ms,
                    created_at=safe.created_at,
                )
            )

    async def list_for_task(self, task_id: UUID) -> list[ToolCallRecord]:
        async with self._session() as session:
            rows = await session.scalars(
                select(ToolCallRow)
                .where(ToolCallRow.task_id == str(task_id))
                .order_by(ToolCallRow.id)
            )
            return [_to_record(row) for row in rows]


class InMemoryToolCallLog:
    """Implements `domain.tools.telemetry.ToolCallLog`."""

    def __init__(self) -> None:
        self.calls: list[ToolCallRecord] = []

    async def record(self, call: ToolCallRecord) -> None:
        self.calls.append(call.redacted())

    async def list_for_task(self, task_id: UUID) -> list[ToolCallRecord]:
        return [call for call in self.calls if call.task_id == task_id]
