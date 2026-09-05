"""The Phase 1 Definition of Done: the CLI runs on a clean machine.

No Docker, no database server, no account.
"""

from __future__ import annotations

from typer.testing import CliRunner

from app.cli.main import app

runner = CliRunner()


def test_version_runs_without_any_infrastructure() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.startswith("kai ")


def test_config_masks_the_provider_key(monkeypatch) -> None:
    from app.config.settings import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("KAI_LLM_API_KEY", "super-secret")
    try:
        result = runner.invoke(app, ["config"])
        assert result.exit_code == 0
        assert "llm_api_key:   set" in result.stdout
        assert "super-secret" not in result.stdout
    finally:
        get_settings.cache_clear()


def test_tasks_reports_an_empty_local_database(monkeypatch, tmp_path) -> None:
    from app.config.settings import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("KAI_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KAI_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'kai.db'}")
    try:
        # The schema has to exist before the repository can read it.
        import asyncio

        from infrastructure.persistence.models import Base
        from infrastructure.persistence.session import create_engine

        async def _create() -> None:
            engine = create_engine(get_settings().resolved_database_url)
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            await engine.dispose()

        asyncio.run(_create())

        result = runner.invoke(app, ["tasks"])
        assert result.exit_code == 0
        assert "No resumable tasks." in result.stdout
    finally:
        get_settings.cache_clear()


def test_tasks_explains_a_missing_schema_instead_of_a_stack_trace(monkeypatch, tmp_path) -> None:
    from app.config.settings import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("KAI_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KAI_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'empty.db'}")
    try:
        result = runner.invoke(app, ["tasks"])
        assert result.exit_code == 1
        assert "no schema yet" in result.output
        assert "alembic upgrade head" in result.output
    finally:
        get_settings.cache_clear()
