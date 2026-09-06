"""The command line, and the command that opens the local interface.

Since Phase 6 the CLI is no longer the only surface: `kai serve` starts the
local interface, which is where a task is normally run and watched. Everything
here still works on its own, because a machine with no browser, or a run started
from a script, must not need one.
"""

from __future__ import annotations

import asyncio
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from uuid import UUID

import typer

from app.config.container import build_container, build_task_runner
from app.config.settings import get_settings
from domain.approvals.models import ApprovalState
from domain.errors import KaiError, StorageNotInitializedError
from domain.llm.models import LLMRequest, Message, RoutingHints, TaskKind
from domain.policies.models import ActorKind, SimpleActor

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
    typer.echo(f"workspace:     {settings.resolved_workspace_dir}")
    typer.echo(f"approvals:     {settings.approval_mode}")
    typer.echo(f"interface:     http://{settings.ui_host}:{settings.ui_port}  (kai serve)")
    typer.echo(
        f"computer use:  {'on' if settings.computer_use_enabled else 'off'} "
        f"(desktop; the browser surface follows the browser tools)"
    )
    typer.echo(f"stop file:     {settings.stop_file_path}")
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


@app.command(name="run-task")
def run_task(
    goal: str = typer.Argument(..., help="What you want done."),
    employee: str = typer.Option("researcher", "--employee", "-e", help="Who should do it."),
) -> None:
    """Give a task to a digital employee and wait for the result."""

    async def _run() -> None:
        container = build_container()
        try:
            await container.sync_employees()
            runner = build_task_runner(container)
            task = await runner.submit_and_run(goal, employee)
            _report(task)
        except KaiError as error:
            typer.secho(f"{type(error).__name__}: {error}", fg="red", err=True)
            raise typer.Exit(code=1) from error
        finally:
            await container.aclose()

    asyncio.run(_run())


@app.command()
def resume() -> None:
    """Pick up every task that was interrupted, from where it stopped."""

    async def _run() -> None:
        container = build_container()
        try:
            await container.sync_employees()
            runner = build_task_runner(container)
            pending = await runner.resumable()
            if not pending:
                typer.echo("Nothing to resume.")
                return
            typer.echo(f"Resuming {len(pending)} task(s).")
            for task in pending:
                typer.secho(f"\n-> {task.goal}", fg="cyan")
                _report(await runner.resume(task))
        except KaiError as error:
            typer.secho(f"{type(error).__name__}: {error}", fg="red", err=True)
            raise typer.Exit(code=1) from error
        finally:
            await container.aclose()

    asyncio.run(_run())


@app.command()
def employees() -> None:
    """List the declared employees.

    Each one is a directory under `employees/`. Nothing here reads a class name.
    """
    container = build_container()
    declared = container.employee_registry.list()
    if not declared:
        typer.echo("No employees declared.")
        return
    for definition in declared:
        typer.secho(f"{definition.name}", fg="cyan", nl=False)
        typer.echo(f"  {definition.role.title}")
        typer.echo(f"  tools:  {', '.join(sorted(definition.allowed_tools)) or 'none'}")
        typer.echo(
            f"  limits: {definition.limits.max_steps} steps, "
            f"${definition.limits.max_cost_usd}, "
            f"{definition.limits.max_wall_time_seconds:.0f}s"
        )


@app.command()
def tools() -> None:
    """Show the tools this machine offers, and who is allowed to call them.

    Least privilege is not a claim to take on trust: this prints, per tool, the
    employees that listed it. A tool nobody lists is a tool nobody can call.
    """
    container = build_container()
    declared = container.employee_registry.list()
    everything = SimpleActor("cli", ActorKind.USER, frozenset({"*"}))

    for spec in container.tool_registry.list_specs(everything):
        users = sorted(d.name for d in declared if spec.name in d.allowed_tools)
        gate = "" if spec.reversible else "  [needs approval]"
        typer.secho(f"{spec.name:<16}", fg="cyan", nl=False)
        typer.echo(
            f"{spec.risk_level.value:<8}{spec.interface_level.value:<14}"
            f"{', '.join(users) or 'nobody'}{gate}"
        )
        typer.echo(f"                 {spec.description.splitlines()[0]}")


@app.command()
def stop(
    reason: str = typer.Option("", "--reason", "-r", help="Why, shown to the employee."),
    clear: bool = typer.Option(False, "--clear", help="Release the brake instead."),
) -> None:
    """Stop anything that is acting on a screen, right now.

    Deliberately not a signal to a process: it writes a file that every action
    on a screen reads before it happens. So it works from a second terminal
    while the first one is busy, it works when the run has the screen, and a
    stop set while nothing is running still holds when the next run starts.
    """
    from infrastructure.computer.stop import FileStopSignal

    signal = FileStopSignal(get_settings().stop_file_path)
    if clear:
        released = signal.release()
        typer.echo(
            "Computer use released." if released else "Computer use was not stopped."
        )
        return
    path = signal.engage(reason)
    typer.secho(f"Computer use stopped: {signal.reason}", fg="yellow")
    typer.echo(f"Release it with: kai stop --clear   ({path})")


@app.command()
def serve(
    host: str = typer.Option("", "--host", help="Override the bind address."),
    port: int = typer.Option(0, "--port", "-p", help="Override the port."),
    reload: bool = typer.Option(False, "--reload", help="Restart on source changes."),
) -> None:
    """Open the local interface: run tasks, watch them, and approve actions.

    One command, one process: the server, the employee runtime and the database
    are the same thing, which is what lets the page park a tool call on a
    question and answer it from a button.
    """
    import uvicorn

    settings = get_settings()
    bind = host or settings.ui_host
    on = port or settings.ui_port
    typer.secho(f"KAI Workforce on http://{bind}:{on}", fg="cyan")
    if bind not in ("127.0.0.1", "localhost", "::1"):
        # Said once, plainly. The interface starts tasks and approves
        # irreversible actions, and it has no authentication because nothing
        # off this machine is supposed to reach it.
        typer.secho(
            f"Warning: {bind} is not loopback. This interface has no "
            "authentication and can start tasks on this machine.",
            fg="yellow",
            err=True,
        )
    uvicorn.run(
        "app.ui.server:create_app",
        factory=True,
        host=bind,
        port=on,
        reload=reload,
        log_level=settings.log_level.lower(),
    )


@app.command()
def approvals() -> None:
    """List the irreversible actions still waiting on a decision."""

    async def _run() -> None:
        container = build_container()
        try:
            pending = await container.approval_repository.list_pending()
            if not pending:
                typer.echo("Nothing is waiting for approval.")
                return
            for approval in pending:
                request = approval.request
                typer.secho(f"{request.id}", fg="yellow")
                typer.echo(f"  action: {request.action}")
                typer.echo(f"  risk:   {request.risk_level.value}")
                typer.echo(f"  task:   {request.task_id}")
                if request.reason:
                    typer.echo(f"  why:    {request.reason}")
        except StorageNotInitializedError as error:
            typer.secho(f"{error} Run: uv run alembic upgrade head", fg="red", err=True)
            raise typer.Exit(code=1) from error
        finally:
            await container.aclose()

    asyncio.run(_run())


@app.command()
def approve(
    approval_id: str = typer.Argument(..., help="The id shown by `kai approvals`."),
    comment: str = typer.Option("", "--comment", "-c", help="Why."),
) -> None:
    """Approve a pending action."""
    _resolve(approval_id, ApprovalState.APPROVED, comment)


@app.command()
def reject(
    approval_id: str = typer.Argument(..., help="The id shown by `kai approvals`."),
    comment: str = typer.Option("", "--comment", "-c", help="Why."),
) -> None:
    """Reject a pending action."""
    _resolve(approval_id, ApprovalState.REJECTED, comment)


def _resolve(approval_id: str, decision: ApprovalState, comment: str) -> None:
    async def _run() -> None:
        container = build_container()
        try:
            service = container.approval_service
            if service is None:
                typer.secho("Approvals are switched off in this configuration.", fg="red")
                raise typer.Exit(code=1)
            await service.resolve(UUID(approval_id), decision, comment=comment)
            typer.secho(f"{decision.value.lower()}: {approval_id}", fg="green")
        except ValueError as error:
            typer.secho(f"'{approval_id}' is not an approval id.", fg="red", err=True)
            raise typer.Exit(code=1) from error
        except KaiError as error:
            typer.secho(f"{type(error).__name__}: {error}", fg="red", err=True)
            raise typer.Exit(code=1) from error
        finally:
            await container.aclose()

    asyncio.run(_run())


def _report(task) -> None:
    from domain.tasks.task import TaskStatus

    colour = {
        TaskStatus.COMPLETED: "green",
        TaskStatus.FAILED: "red",
        TaskStatus.CANCELLED: "yellow",
    }.get(task.status, "white")

    if task.result and task.result.summary:
        typer.echo(f"\n{task.result.summary}")

    typer.secho(f"\n[{task.status}] {task.id}", fg=colour)
    if task.error:
        typer.secho(f"{task.error.kind}: {task.error.message}", fg="red")
    typer.echo(f"steps: {task.execution.step}  cost: ${task.cost_usd:.6f}")


if __name__ == "__main__":
    app()
