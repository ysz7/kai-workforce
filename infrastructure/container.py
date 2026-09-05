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

from domain.approvals.protocols import ApprovalRepository, ApprovalService
from domain.browser.protocols import Browser
from domain.capabilities.models import CapabilityRequirement
from domain.employees.protocols import EmployeeRegistry
from domain.llm.models import RoutingHints, TaskKind
from domain.llm.protocols import LLM, ModelRouter
from domain.llm.telemetry import LLMCallLog
from domain.search.protocols import SearchEngine
from domain.secrets.protocols import SecretResolver
from domain.tasks.repository import TaskRepository
from domain.tools.protocols import ToolRegistry
from domain.tools.telemetry import ToolCallLog
from domain.workforce.repository import AssignmentRepository
from infrastructure.employees.yaml_registry import YamlEmployeeRegistry
from infrastructure.llm.catalog import ModelCatalog
from infrastructure.llm.factory import ProviderFactory
from infrastructure.llm.retry import RetryPolicy
from infrastructure.llm.router import CapabilityAwareModelRouter
from infrastructure.observability.logging import configure_logging, get_logger
from infrastructure.persistence.in_memory_task_repository import InMemoryTaskRepository
from infrastructure.persistence.session import create_engine, create_session_factory
from infrastructure.secrets.env import EnvSecretResolver
from infrastructure.settings import RuntimeSettings
from infrastructure.tools.builtin import build_registry


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

    @cached_property
    def llm_call_log(self) -> LLMCallLog:
        if self._in_memory:
            from infrastructure.persistence.llm_call_repository import InMemoryLLMCallLog

            return InMemoryLLMCallLog()
        from infrastructure.persistence.llm_call_repository import SqliteLLMCallLog

        return SqliteLLMCallLog(self.session_factory)

    # --- Models ---------------------------------------------------------------

    @cached_property
    def model_catalog(self) -> ModelCatalog:
        return ModelCatalog.load(self.settings.model_catalog_path)

    @cached_property
    def model_router(self) -> ModelRouter:
        return CapabilityAwareModelRouter(self.model_catalog)

    @cached_property
    def llm_factory(self) -> ProviderFactory:
        return ProviderFactory(
            catalog=self.model_catalog,
            api_key=self.settings.llm_api_key,
            base_url=self.settings.llm_base_url,
            local_base_url=self.settings.local_llm_base_url,
            call_log=self.llm_call_log,
            retry_policy=RetryPolicy(attempts=self.settings.llm_retry_attempts),
        )

    def llm_for(
        self,
        task_kind: TaskKind,
        requirement: CapabilityRequirement | None = None,
        hints: RoutingHints | None = None,
    ) -> LLM:
        """Pick a model for a piece of work and hand back a client for it."""
        choice = self.model_router.select(
            task_kind, requirement or CapabilityRequirement(), hints
        )
        # Debug, not info: clients are built when the runtime is assembled, so at
        # info level this reads as though the work happened, and muddies a trace.
        self.logger.debug(
            "llm.routed", task_kind=str(task_kind), model=choice.model, reason=choice.reason
        )
        return self.llm_factory.for_choice(choice)

    # --- Workforce ------------------------------------------------------------

    @cached_property
    def employee_registry(self) -> EmployeeRegistry:
        return YamlEmployeeRegistry(self.settings.employees_dir)

    # --- Tools ----------------------------------------------------------------

    @cached_property
    def secret_resolver(self) -> SecretResolver:
        return EnvSecretResolver()

    @cached_property
    def search_engine(self) -> SearchEngine:
        from infrastructure.search.duckduckgo import DuckDuckGoSearch

        return DuckDuckGoSearch(timeout_seconds=self.settings.browser_timeout_seconds)

    @cached_property
    def browser(self) -> Browser:
        from infrastructure.browser.playwright_browser import PlaywrightBrowser

        return PlaywrightBrowser(
            self.search_engine,
            headless=self.settings.browser_headless,
            timeout_seconds=self.settings.browser_timeout_seconds,
        )

    @cached_property
    def tool_registry(self) -> ToolRegistry:
        """Everything this machine can do. Who may do what is settled per employee.

        The callables are passed rather than the objects: a workforce that never
        opens a page never launches a browser, and never imports Playwright.
        """
        self.configure()
        return build_registry(
            workspace_root=self.settings.ensure_workspace_dir(),
            search_engine=(
                (lambda: self.search_engine) if self.settings.browser_tools_enabled else None
            ),
            browser=(lambda: self.browser) if self.settings.browser_tools_enabled else None,
            code_execution=self.settings.code_execution_enabled,
            code_timeout_seconds=self.settings.code_timeout_seconds,
        )

    @cached_property
    def tool_call_log(self) -> ToolCallLog:
        if self._in_memory:
            from infrastructure.persistence.tool_call_repository import InMemoryToolCallLog

            return InMemoryToolCallLog()
        from infrastructure.persistence.tool_call_repository import SqliteToolCallLog

        return SqliteToolCallLog(self.session_factory)

    # --- Approvals --------------------------------------------------------------

    @cached_property
    def approval_repository(self) -> ApprovalRepository:
        if self._in_memory:
            from infrastructure.persistence.approval_repository import (
                InMemoryApprovalRepository,
            )

            return InMemoryApprovalRepository()
        from infrastructure.persistence.approval_repository import SqliteApprovalRepository

        return SqliteApprovalRepository(self.session_factory)

    @cached_property
    def approval_service(self) -> ApprovalService | None:
        """None means nobody can be asked - and so nothing irreversible happens."""
        if not self.settings.approvals_enabled:
            return None
        from infrastructure.approvals.service import LocalApprovalService

        return LocalApprovalService(
            self.approval_repository, mode=self.settings.approval_mode
        )

    @cached_property
    def employee_repository(self):
        if self._in_memory:
            from infrastructure.persistence.employee_repository import (
                InMemoryEmployeeRepository,
            )

            return InMemoryEmployeeRepository()
        from infrastructure.persistence.employee_repository import SqliteEmployeeRepository

        return SqliteEmployeeRepository(self.session_factory)

    async def sync_employees(self) -> int:
        """Persist the declared employees so tasks can reference them.

        Called before running anything: the declarations are the source of
        truth, and the table has to know about an employee before a task can be
        assigned to it.
        """
        return await self.employee_repository.sync(self.employee_registry.list())

    @cached_property
    def assignment_repository(self) -> AssignmentRepository:
        if self._in_memory:
            from infrastructure.persistence.assignment_repository import (
                InMemoryAssignmentRepository,
            )

            return InMemoryAssignmentRepository()
        from infrastructure.persistence.assignment_repository import (
            SqliteAssignmentRepository,
        )

        return SqliteAssignmentRepository(self.session_factory)

    async def aclose(self) -> None:
        if "llm_factory" in self.__dict__:
            await self.llm_factory.aclose()
        # Only what was actually built: a run that never searched has no client
        # to close, and asking for one here would create it in order to do so.
        for name in ("browser", "search_engine"):
            resource = self.__dict__.get(name)
            if resource is not None:
                await resource.aclose()
        if "engine" in self.__dict__:
            await self.engine.dispose()
