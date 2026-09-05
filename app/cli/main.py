"""The CLI is the only interface until the local UI arrives in Phase 6."""

from __future__ import annotations

import asyncio
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version

import typer

from app.config.container import build_container
from app.config.settings import get_settings
from domain.errors import KaiError, StorageNotInitializedError
from domain.llm.models import LLMRequest, Message, RoutingHints, TaskKind

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
def ask(
    question: str = typer.Argument(..., help="What to ask."),
    system: str = typer.Option(
        "", "--system", "-s", help="Optional system prompt."
    ),
) -> None:
    """Ask a model a question and report what it cost.

    This is Phase 2's validation: a real answer through a real provider, with
    the price of it on screen. Cost is shown from the first call because local
    development pays for every token.
    """

    async def _run() -> None:
        container = build_container()
        try:
            settings = container.settings
            client = container.llm_for(
                TaskKind.CONVERSATION, hints=RoutingHints(quality=0.7)
            )
            messages = [Message.user(question)]
            if system:
                messages.insert(0, Message.system(system))
            elif settings.response_language != "en":
                messages.insert(
                    0, Message.system(f"Answer in {settings.response_language}.")
                )

            response = await client.generate(
                LLMRequest(messages=tuple(messages), temperature=0.3)
            )
            typer.echo(response.content)
            usage = response.usage
            typer.secho(
                f"\n[{response.model}] {usage.prompt_tokens} in / {usage.output_tokens} out"
                f" - ${usage.cost_usd:.6f} - {usage.latency_ms} ms",
                fg="cyan",
            )
        except KaiError as error:
            typer.secho(f"{type(error).__name__}: {error}", fg="red", err=True)
            raise typer.Exit(code=1) from error
        finally:
            await container.aclose()

    asyncio.run(_run())


@app.command()
def spend() -> None:
    """Show what has been spent on models so far."""

    async def _run() -> None:
        container = build_container()
        try:
            summary = await container.llm_call_log.total()
            typer.echo(f"calls:         {summary.calls}")
            typer.echo(f"prompt tokens: {summary.prompt_tokens}")
            typer.echo(f"output tokens: {summary.output_tokens}")
            typer.echo(f"cost:          ${summary.cost_usd:.6f}")
        except StorageNotInitializedError as error:
            typer.secho(
                f"{error} Run: uv run alembic upgrade head", fg="red", err=True
            )
            raise typer.Exit(code=1) from error
        finally:
            await container.aclose()

    asyncio.run(_run())


@app.command()
def models() -> None:
    """Show the model catalog and which entry each kind of work defaults to."""
    container = build_container()
    catalog = container.model_catalog
    defaults = {name: kind for kind, name in catalog.defaults.items()}

    for entry in catalog.entries:
        default_for = [k.value.lower() for k, n in catalog.defaults.items() if n == entry.name]
        marker = f"  <- default for {', '.join(sorted(default_for))}" if default_for else ""
        typer.echo(f"{entry.name:<10} {entry.provider}/{entry.model}{marker}")
        typer.echo(
            f"           ${entry.input_cost_per_1k_usd}/1k in, "
            f"${entry.output_cost_per_1k_usd}/1k out, "
            f"{entry.context_tokens} ctx"
        )
    if not defaults:
        typer.echo("No defaults configured.")


@app.command()
def employees() -> None:
    """List the declared employees."""
    # The registry lands in Phase 3, together with the runtime that uses it.
    typer.echo("No employees yet: the registry arrives in Phase 3.")


if __name__ == "__main__":
    app()
