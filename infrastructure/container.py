"""Dependency wiring.

Dependencies are built lazily: a CLI call that only prints the version must not
open a database file, and a test that only needs a repository must not configure
a provider.

The container does not read configuration - it is handed the settings it needs.
That keeps `infrastructure` from importing `app`, which owns configuration.
"""

from __future__ import annotations

from functools import cached_property

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from domain.tasks.repository import TaskRepository
from infrastructure.observability.logging import configure_logging, get_logger
from infrastructure.persistence.in_memory_task_repository import InMemoryTaskRepository
from infrastructure.persistence.session import create_engine, create_session_factory
from infrastructure.settings import RuntimeSettings


class Container:
    def __init__(self, settings: RuntimeSettings, *, in_memory: bool = False) -> None:
        self.settings = settings
        self._in_memory = in_memory
        self._configured_logging = False

    # --- Cross-cutting --------------------------------------------------------

    def configure(self) -> None:
        """Idempotent start-up: logging, and the data directory the DB lives in."""
        if not self._configured_logging:
            configure_logging(self.settings.log_level, self.settings.log_format)
            self._configured_logging = True
        if not self._in_memory:
            self.settings.ensure_data_dir()

    @cached_property
    def logger(self):
        # structlog's bound logger type is not stable enough to annotate.
        self.configure()
        return get_logger("kai")

    # --- Persistence ----------------------------------------------------------

    @cached_property
    def engine(self) -> AsyncEngine:
        self.configure()
        return create_engine(self.settings.resolved_database_url)

    @cached_property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        return create_session_factory(self.engine)

    @cached_property
    def task_repository(self) -> TaskRepository:
        if self._in_memory:
            return InMemoryTaskRepository()
        # Imported here so an in-memory container never pulls in the SQL adapter.
        from infrastructure.persistence.task_repository import SqliteTaskRepository

        return SqliteTaskRepository(self.session_factory)

    async def aclose(self) -> None:
        if "engine" in self.__dict__:
            await self.engine.dispose()
