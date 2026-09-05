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


def test_models_lists_the_catalog_and_its_defaults() -> None:
    result = runner.invoke(app, ["models"])
    assert result.exit_code == 0
    assert "default for" in result.output


def test_ask_without_a_key_explains_itself_instead_of_calling_out(monkeypatch) -> None:
    from app.config.settings import get_settings

    get_settings.cache_clear()
    monkeypatch.delenv("KAI_LLM_API_KEY", raising=False)
    try:
        result = runner.invoke(app, ["ask", "Which city?"])
        assert result.exit_code == 1
        assert "KAI_LLM_API_KEY" in result.output
    finally:
        get_settings.cache_clear()


def test_spend_reports_zero_on_a_fresh_database(monkeypatch, tmp_path) -> None:
    import asyncio

    from app.config.settings import get_settings
    from infrastructure.persistence.models import Base
    from infrastructure.persistence.session import create_engine

    get_settings.cache_clear()
    monkeypatch.setenv("KAI_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KAI_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'kai.db'}")
    try:

        async def _create() -> None:
            engine = create_engine(get_settings().resolved_database_url)
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            await engine.dispose()

        asyncio.run(_create())

        result = runner.invoke(app, ["spend"])
        assert result.exit_code == 0
        assert "calls:         0" in result.output
        assert "$0.000000" in result.output
    finally:
        get_settings.cache_clear()


def test_tools_shows_who_may_call_each_tool(monkeypatch, tmp_path) -> None:
    """Least privilege is printable: the user can see the grants, not trust them."""
    from app.config.settings import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("KAI_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KAI_WORKSPACE_DIR", str(tmp_path / "workspace"))
    try:
        result = runner.invoke(app, ["tools"])
        assert result.exit_code == 0
        assert "fs.move" in result.output
        assert "organizer" in result.output
        # Nobody declares code.run, so nobody can call it.
        assert "code.run" in result.output
        assert "nobody" in result.output
    finally:
        get_settings.cache_clear()


def test_approvals_reports_an_empty_queue(monkeypatch, tmp_path) -> None:
    import asyncio

    from app.config.settings import get_settings
    from infrastructure.persistence.models import Base
    from infrastructure.persistence.session import create_engine

    get_settings.cache_clear()
    monkeypatch.setenv("KAI_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KAI_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'kai.db'}")
    try:

        async def _create() -> None:
            engine = create_engine(get_settings().resolved_database_url)
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            await engine.dispose()

        asyncio.run(_create())

        result = runner.invoke(app, ["approvals"])
        assert result.exit_code == 0
        assert "Nothing is waiting for approval." in result.output
    finally:
        get_settings.cache_clear()


def test_an_id_that_is_not_an_id_is_reported_plainly(monkeypatch, tmp_path) -> None:
    from app.config.settings import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("KAI_DATA_DIR", str(tmp_path))
    try:
        result = runner.invoke(app, ["approve", "not-a-uuid"])
        assert result.exit_code == 1
    finally:
        get_settings.cache_clear()
