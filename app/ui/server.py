"""The local interface: one page, on loopback, with no account behind it.

Phase 6's Definition of Done is that a developer uses KAI without reading logs
in a terminal. That is a statement about what the page shows, so the endpoints
here exist to answer four questions and no more: what can I ask for, what is it
doing right now, what does it need from me, and what happened last time.

Since Phase 7 the first of those has a different answer. The page asks *KAI* for
an outcome; the manager decides what tasks that means and who does each. The
task endpoints stay, because a task is still the unit that runs and the trace is
still drawn from one - but starting work now means stating a goal, not choosing
an employee.

**It binds to 127.0.0.1 and has no authentication.** Those two facts are one
decision, not two. The interface starts tasks, approves irreversible actions and
can stop the machine's screen; it is safe without a password precisely because
nothing off this machine can reach it. Binding it anywhere else would turn a
local tool into an unauthenticated remote one, which is why the host is a
setting that documents itself rather than a command-line flag inviting `0.0.0.0`.

**The trace is pushed, not polled.** Server-sent events, because the traffic is
one-way - the server describes, the browser draws - and SSE reconnects on its
own, needs no library, and survives the page being left open while nothing runs.
A websocket would buy a direction nobody uses.

**Approvals are answered here, and the run really is parked.** The tool call
waits on a future (`WaitingConfirmer`); this hands it the answer. Nothing is
approved by default, by timeout, or by the page being closed.

The container, the runner and the live runs are per-application, created at
startup and closed at shutdown, so the browser talking to a dead engine is not a
state this can be in.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config.container import build_container, build_manager, build_task_runner
from app.config.settings import Settings, get_settings
from app.ui import views
from app.ui.runs import Runs
from domain.approvals.models import ApprovalState
from domain.errors import KaiError, StorageNotInitializedError
from domain.tasks.progress import ProgressKind
from infrastructure.approvals.waiting import WaitingConfirmer
from infrastructure.container import Container

log = structlog.get_logger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

#: How long the event stream waits before sending a comment line. Without it a
#: proxy or a sleeping laptop can drop an idle connection with nothing to show
#: for it, and the page would sit silently on a stream that is already dead.
HEARTBEAT_SECONDS = 15.0


class NewTask(BaseModel):
    goal: str = Field(min_length=1)
    employee: str = Field(min_length=1)


class NewObjective(BaseModel):
    request: str = Field(min_length=1)


class Decision(BaseModel):
    approved: bool
    comment: str = ""


class Cancellation(BaseModel):
    reason: str = ""


def create_app(
    settings: Settings | None = None,
    *,
    build: Callable[[Settings], Container] = build_container,
) -> FastAPI:
    """Build the interface around its own container.

    Settings and the way the container is built are both arguments, for the same
    reason the container is handed its settings rather than reading them: it is
    what lets the whole interface be exercised against a temporary database and
    a scripted model, with no server running and no provider key configured.
    """
    resolved = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        container = build(resolved)
        # Set before anything can ask: an approval that reached stdin while the
        # person is looking at a browser is an approval nobody can answer.
        confirmer = WaitingConfirmer(
            timeout_seconds=resolved.ui_approval_timeout_seconds,
            progress=container.progress,
        )
        container.use_approval_confirmer(confirmer)
        await container.sync_employees()

        app.state.settings = resolved
        app.state.container = container
        app.state.confirmer = confirmer
        app.state.runs = Runs(
            runner=build_task_runner(container),
            manager=build_manager(container),
            tasks=container.task_repository,
            cancellations=container.cancellations,
            approvals=confirmer,
        )
        log.info("ui.started", host=resolved.ui_host, port=resolved.ui_port)
        try:
            yield
        finally:
            await app.state.runs.aclose()
            await container.aclose()

    app = FastAPI(title="KAI Workforce", lifespan=lifespan, docs_url=None, redoc_url=None)
    _routes(app)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


# --- Routes -------------------------------------------------------------------


def _routes(app: FastAPI) -> None:
    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/employees")
    async def employees(request: Request) -> dict[str, Any]:
        registry = _container(request).employee_registry
        return {"employees": [views.employee(d) for d in registry.list()]}

    @app.get("/api/tasks")
    async def history(request: Request) -> dict[str, Any]:
        runs = _runs(request)
        settings: Settings = request.app.state.settings
        tasks = await _guarded(
            _container(request).task_repository.list_recent(limit=settings.ui_history_limit)
        )
        return {
            "tasks": [views.task_summary(t, running=runs.is_running(t.id)) for t in tasks]
        }

    @app.post("/api/tasks", status_code=201)
    async def start(request: Request, body: NewTask) -> dict[str, Any]:
        try:
            task = await _runs(request).start(body.goal.strip(), body.employee)
        except KaiError as error:
            # An unknown employee is the user asking for something that does not
            # exist, not a server fault: 400, with the reason said plainly.
            raise HTTPException(status_code=400, detail=str(error)) from error
        return views.task_summary(task, running=True)

    @app.get("/api/tasks/{task_id}")
    async def detail(request: Request, task_id: UUID) -> dict[str, Any]:
        container = _container(request)
        task = await _guarded(container.task_repository.get(task_id))
        if task is None:
            raise HTTPException(status_code=404, detail=f"Unknown task: {task_id}")
        names = {d.id: d.name for d in container.employee_registry.list()}
        return views.task_detail(
            task,
            running=_runs(request).is_running(task_id),
            calls=await _guarded(container.tool_call_log.list_for_task(task_id)),
            events=await _guarded(container.task_repository.events(task_id)),
            employee=names.get(task.assigned_employee_id) if task.assigned_employee_id else None,
        )

    @app.post("/api/tasks/{task_id}/cancel")
    async def cancel(request: Request, task_id: UUID, body: Cancellation) -> dict[str, Any]:
        task = await _runs(request).cancel(task_id, body.reason)
        if task is None:
            raise HTTPException(status_code=404, detail=f"Unknown task: {task_id}")
        return views.task_summary(task, running=_runs(request).is_running(task_id))

    # --- The manager ----------------------------------------------------------

    @app.post("/api/objectives", status_code=201)
    async def ask(request: Request, body: NewObjective) -> dict[str, Any]:
        """State a goal. KAI decides what it means and who does it."""
        objective = await _runs(request).ask(body.request.strip())
        return views.objective_summary(objective, thinking=True)

    @app.get("/api/objectives")
    async def objectives(request: Request) -> dict[str, Any]:
        runs = _runs(request)
        settings: Settings = request.app.state.settings
        recent = await _guarded(
            _container(request).objective_repository.list_recent(
                limit=settings.ui_history_limit
            )
        )
        return {
            "objectives": [
                views.objective_summary(item, thinking=runs.is_thinking(item.id))
                for item in recent
            ]
        }

    @app.get("/api/objectives/{objective_id}")
    async def objective(request: Request, objective_id: UUID) -> dict[str, Any]:
        container = _container(request)
        item = await _guarded(container.objective_repository.get(objective_id))
        if item is None:
            raise HTTPException(status_code=404, detail=f"Unknown objective: {objective_id}")
        return views.objective_detail(
            item,
            thinking=_runs(request).is_thinking(objective_id),
            plans=await _guarded(container.plan_repository.for_objective(objective_id)),
        )

    @app.post("/api/objectives/{objective_id}/cancel")
    async def stop_objective(request: Request, objective_id: UUID) -> dict[str, Any]:
        stopped = await _runs(request).cancel_objective(objective_id)
        item = await _guarded(_container(request).objective_repository.get(objective_id))
        if item is None:
            raise HTTPException(status_code=404, detail=f"Unknown objective: {objective_id}")
        return {**views.objective_summary(item), "stopped": stopped}

    @app.get("/api/approvals")
    async def approvals(request: Request) -> dict[str, Any]:
        """What is waiting, live first.

        The pending rows are read too, because a question left behind by a
        killed run is still an open decision - it is simply one that no tool
        call is parked on, and the page says which is which.
        """
        confirmer: WaitingConfirmer = request.app.state.confirmer
        live = {item.id: item for item in confirmer.pending()}
        stored = await _guarded(_container(request).approval_repository.list_pending())
        return {
            "approvals": [views.approval(item, live=True) for item in live.values()]
            + [
                views.stored_approval(record)
                for record in stored
                if record.id not in live
            ]
        }

    @app.post("/api/approvals/{approval_id}")
    async def decide(request: Request, approval_id: UUID, body: Decision) -> dict[str, Any]:
        state = ApprovalState.APPROVED if body.approved else ApprovalState.REJECTED
        answered = _runs(request).decide(approval_id, body.approved)
        if not answered:
            # Nothing is parked on it here. Record the decision anyway, so a row
            # from a killed run stops showing up as an open question.
            service = _container(request).approval_service
            if service is None:
                raise HTTPException(
                    status_code=409, detail="Approvals are switched off in this configuration."
                )
            try:
                await service.resolve(approval_id, state, comment=body.comment)
            except KaiError as error:
                raise HTTPException(status_code=404, detail=str(error)) from error
        return {"id": str(approval_id), "state": state.value, "live": answered}

    @app.get("/api/spend")
    async def spend(request: Request) -> dict[str, Any]:
        summary = await _guarded(_container(request).llm_call_log.total())
        return {
            "calls": summary.calls,
            "prompt_tokens": summary.prompt_tokens,
            "output_tokens": summary.output_tokens,
            "cost_usd": round(summary.cost_usd, 6),
        }

    @app.get("/api/events")
    async def events(
        request: Request, task: UUID | None = None, objective: UUID | None = None
    ) -> StreamingResponse:
        stream = (
            _objective_stream(request, objective)
            if objective is not None
            else _event_stream(request, task)
        )
        return StreamingResponse(
            stream,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )


# --- The stream ---------------------------------------------------------------


async def _event_stream(request: Request, task_id: UUID | None) -> AsyncIterator[str]:
    """Everything announced from now on, plus the little that came just before.

    The replay is what makes opening the page mid-run useful rather than
    confusing; it is bounded by the broadcaster's buffer and is never the record
    of what happened - that is the task row and the tool-call log.

    A stream watching one task ends when that task does. A finished run has
    nothing further to say, and a connection held open on one is a connection
    the page has to be told to ignore; ending it means the browser learns the
    run is over from the stream itself. The subscription is taken out before the
    task's state is read, so a run that finishes between the two is reported,
    not missed. The unfiltered stream - what the page watches for approvals
    raised by tasks it is not showing - has no such end and stays open.
    """
    broadcaster = request.app.state.container.progress
    async with broadcaster.subscribe() as queue:
        finished = False
        if task_id is not None:
            try:
                watched = await request.app.state.container.task_repository.get(task_id)
            except StorageNotInitializedError:
                # Every other endpoint says so plainly; a stream cannot, and
                # ending it here would look like a task that had finished.
                watched = None
            finished = watched is not None and watched.is_terminal
            for past in broadcaster.recent(task_id):
                yield _sse(past.to_dict())
            if finished:
                return
        while True:
            if await request.is_disconnected():
                return
            try:
                event = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
            except TimeoutError:
                yield ": keep-alive\n\n"
                continue
            if task_id is not None and event.task_id != task_id:
                continue
            yield _sse(event.to_dict())
            if task_id is not None and event.kind is ProgressKind.RESULT:
                return


async def _objective_stream(request: Request, objective_id: UUID) -> AsyncIterator[str]:
    """One objective's progress, and that of every task it starts.

    KAI stamps its own events with the objective. Its employees do not - they
    are running tasks and know nothing about a manager - so the task ids belong
    to the objective's plan, and this follows them: seeded from whatever plan
    revisions already exist, and extended whenever KAI announces a task it has
    just handed out. That is what makes the trace read as one piece of work
    rather than as a manager talking to itself.

    It ends when the objective does, for the same reason a task stream ends when
    its task does.
    """
    container = request.app.state.container
    broadcaster = container.progress
    async with broadcaster.subscribe() as queue:
        tracked = await _tasks_of(container, objective_id)
        item = await _objective_or_none(container, objective_id)
        finished = item is not None and item.is_terminal

        for past in broadcaster.recent(objective_id):
            _track(tracked, past)
            yield _sse(past.to_dict())
        for task_id in sorted(tracked, key=str):
            for past in broadcaster.recent(task_id):
                yield _sse(past.to_dict())
        if finished:
            return

        while True:
            if await request.is_disconnected():
                return
            try:
                event = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
            except TimeoutError:
                yield ": keep-alive\n\n"
                continue
            mine = event.objective_id == objective_id
            if not mine and event.task_id not in tracked:
                continue
            if mine:
                _track(tracked, event)
            yield _sse(event.to_dict())
            if mine and event.kind is ProgressKind.RESULT:
                return


def _track(tracked: set[UUID], event) -> None:
    """Follow a task the manager has just announced it delegated."""
    raw = event.payload.get("task_id")
    if raw:
        tracked.add(UUID(str(raw)))
    for task in event.payload.get("tasks") or ():
        if isinstance(task, dict) and task.get("id"):
            tracked.add(UUID(str(task["id"])))


async def _tasks_of(container, objective_id: UUID) -> set[UUID]:
    try:
        plans = await container.plan_repository.for_objective(objective_id)
    except StorageNotInitializedError:
        return set()
    return {task.id for plan in plans for task in plan.tasks}


async def _objective_or_none(container, objective_id: UUID):
    try:
        return await container.objective_repository.get(objective_id)
    except StorageNotInitializedError:
        return None


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload)}\n\n"


# --- Helpers ------------------------------------------------------------------


def _container(request: Request):
    return request.app.state.container


def _runs(request: Request) -> Runs:
    return request.app.state.runs


async def _guarded(awaitable):
    """Turn "there is no schema yet" into an answer instead of a stack trace."""
    try:
        return await awaitable
    except StorageNotInitializedError as error:
        raise HTTPException(
            status_code=503,
            detail=f"{error} Run: uv run alembic upgrade head",
        ) from error
