from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from infrastructure.persistence.models import Base
from infrastructure.persistence.session import create_engine, create_session_factory
from infrastructure.persistence.task_repository import SqliteTaskRepository


@pytest_asyncio.fixture
async def session_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """A real SQLite file, not an in-memory database.

    The point of these tests is that work survives a restart, and a shared
    in-memory database would not exercise that.
    """
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield create_session_factory(engine)
    await engine.dispose()


@pytest.fixture
def sqlite_repository(session_factory: async_sessionmaker[AsyncSession]) -> SqliteTaskRepository:
    return SqliteTaskRepository(session_factory)
