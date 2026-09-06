from __future__ import annotations

from pathlib import Path

from infrastructure.container import Container
from infrastructure.persistence.in_memory_task_repository import InMemoryTaskRepository


class StubSettings:
    """Anything satisfying `RuntimeSettings` will do; no environment involved."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.log_level = "INFO"
        self.log_format = "json"
        self.ensured = False

    @property
    def resolved_database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.data_dir / 'kai.db'}"

    def ensure_data_dir(self) -> Path:
        self.ensured = True
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir


def test_nothing_is_built_until_it_is_asked_for(tmp_path: Path) -> None:
    settings = StubSettings(tmp_path / "data")
    container = Container(settings)

    assert "engine" not in container.__dict__
    assert not settings.ensured
    assert not (tmp_path / "data").exists(), "constructing a container touches no disk"


def test_the_engine_is_created_once_and_cached(tmp_path: Path) -> None:
    container = Container(StubSettings(tmp_path))
    assert container.engine is container.engine


def test_an_in_memory_container_never_reaches_for_storage(tmp_path: Path) -> None:
    settings = StubSettings(tmp_path / "data")
    container = Container(settings, in_memory=True)

    assert isinstance(container.task_repository, InMemoryTaskRepository)
    container.configure()
    assert not settings.ensured


def test_the_configured_model_timeout_reaches_the_provider(tmp_path: Path) -> None:
    """A setting that is documented and never read is worse than no setting.

    This one was exactly that until Phase 8: `.env.example` described it,
    `Settings` held it, and nothing passed it on - so a local model that needed
    longer was cut off at whatever the adapter happened to default to.
    """
    from domain.capabilities.models import CapabilityRequirement
    from domain.llm.models import TaskKind
    from infrastructure.llm.catalog import ModelCatalog
    from infrastructure.llm.factory import ProviderFactory
    from infrastructure.llm.local import DEFAULT_TIMEOUT_SECONDS
    from infrastructure.llm.router import CapabilityAwareModelRouter

    catalog = ModelCatalog.load(
        Path(__file__).resolve().parents[2] / "infrastructure/llm/models.local.toml"
    )
    choice = CapabilityAwareModelRouter(catalog).select(
        TaskKind.EXECUTION, CapabilityRequirement(), None
    )

    configured = ProviderFactory(catalog=catalog, api_key=None, base_url="", timeout_seconds=42.0)
    assert configured._build(choice)._timeout == 42.0

    # Unset means the provider's own default, which is not one number: a local
    # model gets minutes where a hosted one gets two.
    default = ProviderFactory(catalog=catalog, api_key=None, base_url="")
    assert default._build(choice)._timeout == DEFAULT_TIMEOUT_SECONDS
