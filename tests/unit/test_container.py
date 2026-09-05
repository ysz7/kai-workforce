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
