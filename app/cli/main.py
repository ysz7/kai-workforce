"""The CLI is the only interface until the local UI arrives in Phase 6."""

from __future__ import annotations

import asyncio
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version

import typer

from app.config.container import build_container
from app.config.settings import get_settings
from domain.errors import StorageNotInitializedError

app = typer.Typer(
    name="kai",
    help="KAI Workforce - run digital employees on your own machine.",
    no_args_is_help=True,
    add_completion=False,
)


def _version() -> str:
    try:
        return package_version("kai-workforce")
    except PackageNotFoundError:
        return "0.1.0"


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"kai {_version()}")
        raise typer.Exit


@app.callback()
def main(
    _version_flag: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Show the version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """KAI Workforce command line."""


@app.command()
def config() -> None:
    """Show the resolved configuration, with secrets masked."""
    settings = get_settings()
    typer.echo(f"data_dir:      {settings.data_dir}")
    typer.echo(f"database:      {settings.resolved_database_url}")
    typer.echo(f"llm_base_url:  {settings.llm_base_url}")
    typer.echo(f"llm_api_key:   {'set' if settings.llm_api_key else 'not set'}")
    typer.echo(f"default_model: {settings.llm_default_model}")
    typer.echo(f"log:           {settings.log_level} ({settings.log_format})")


@app.command()
def tasks() -> None:
    """List the tasks that would be picked up again after a restart."""

    async def _run() -> None:
        container = build_container()
        try:
            try:
                resumable = await container.task_repository.list_resumable()
            except StorageNotInitializedError as error:
                # A fresh checkout has no schema yet; say so instead of a stack trace.
                typer.secho(
                    f"{error} Run: uv run alembic upgrade head", fg="red", err=True
                )
                raise typer.Exit(code=1) from error
            if not resumable:
                typer.echo("No resumable tasks.")
                return
            for task in resumable:
                typer.echo(f"{task.id}  {task.status:<20} {task.goal}")
        finally:
            await container.aclose()

    asyncio.run(_run())


@app.command()
def employees() -> None:
    """List the declared employees."""
    # The registry lands in Phase 3, together with the runtime that uses it.
    typer.echo("No employees yet: the registry arrives in Phase 3.")


if __name__ == "__main__":
    app()
