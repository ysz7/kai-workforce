"""The Phase 3 Definition of Done: kill a task mid-run, and it continues.

Not "starts again" - continues. The transcript, the step cursor and what has
already been spent all survive, because they are written to the task after every
step rather than at the end.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from application.employee_runtime.executor import Executor
from application.employee_runtime.planner import Planner
from application.employee_runtime.runtime import EmployeeRuntime, RuntimeDependencies
from application.employee_runtime.transcript import RunState
from application.employee_runtime.verifier import Verifier
from domain.errors import ProviderUnavailableError
from domain.llm.models import ToolCallRequest
from domain.tasks.task import Task, TaskStatus
from infrastructure.persistence.models import Base
from infrastructure.persistence.session import create_engine, create_session_factory
from infrastructure.persistence.task_repository import SqliteTaskRepository
from infrastructure.tools.registry import InMemoryToolRegistry
from tests.fakes.employees import definition
from tests.fakes.llm import FakeLLM, reply, tool_reply
from tests.fakes.tools import FakeTool

PLAN = reply('{"steps": [{"description": "Read the file", "expected_outcome": "its contents"}]}')
PASS = reply('{"passed": true, "reason": "complete"}')

EMPLOYEE = definition(tools=frozenset({"fs.read"}))


def build_runtime(llm: FakeLLM, tasks: SqliteTaskRepository) -> EmployeeRuntime:
    """A fresh runtime, as a restarted process would build."""
    registry = InMemoryToolRegistry([FakeTool("fs.read", description="Read a file")])
    return EmployeeRuntime(
        EMPLOYEE,
        RuntimeDependencies(
            planner=Planner(llm),
            executor=Executor(llm, registry),
            verifier=Verifier(llm),
            tasks=tasks,
            tools=registry,
            limits=EMPLOYEE.limits,
            system_prompt=EMPLOYEE.system_prompt,
        ),
    )


async def test_a_task_killed_mid_run_continues_from_its_last_step(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'kai.db'}"

    # --- First process: plan, take one step, then die. ------------------------
    engine = create_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    tasks = SqliteTaskRepository(create_session_factory(engine))

    task = Task.create("Read a.txt and tell me what is in it")
    await tasks.save(task)

    crashing = FakeLLM(
        [
            PLAN,
            tool_reply(ToolCallRequest(id="c1", name="fs.read", arguments={"path": "a.txt"})),
            ProviderUnavailableError("the machine went down"),
        ]
    )
    with pytest.raises(ProviderUnavailableError):
        await build_runtime(crashing, tasks).run(task)

    await engine.dispose()

    # --- What survived the crash ---------------------------------------------
    engine = create_engine(database_url)
    tasks = SqliteTaskRepository(create_session_factory(engine))

    interrupted = await tasks.get(task.id)
    assert interrupted.status is TaskStatus.RUNNING
    assert interrupted.is_resumable
    assert interrupted.execution.step == 1, "one step was completed and saved"

    saved = RunState.from_state(interrupted.execution.state)
    assert saved.stage == "EXECUTING", "it resumes into execution, not back into planning"
    assert len(saved.transcript.observations) == 1
    assert "fs.read" in saved.transcript.observations[0].summary
    assert interrupted.plan is not None, "the plan was not lost"

    # --- Second process: pick it up and finish. -------------------------------
    resuming = FakeLLM([reply("The file contains hello."), PASS])
    await build_runtime(resuming, tasks).run(interrupted)

    completed = await tasks.get(task.id)
    assert completed.status is TaskStatus.COMPLETED
    assert completed.result.summary == "The file contains hello."

    # It continued rather than restarted: the resumed process never re-planned,
    # and the tool result from before the crash was still in the transcript.
    assert resuming.call_count == 2
    first_resumed_request = resuming.requests[0]
    tool_messages = [m for m in first_resumed_request.messages if m.role.value == "tool"]
    assert len(tool_messages) == 1, "the pre-crash tool result came back with it"

    await engine.dispose()


async def test_resuming_does_not_pay_for_the_work_again(tmp_path: Path) -> None:
    from dataclasses import replace

    from domain.llm.models import Usage

    database_url = f"sqlite+aiosqlite:///{tmp_path / 'kai.db'}"
    engine = create_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    tasks = SqliteTaskRepository(create_session_factory(engine))

    task = Task.create("Read a.txt")
    await tasks.save(task)

    expensive_step = replace(
        tool_reply(ToolCallRequest(id="c1", name="fs.read", arguments={})),
        usage=Usage(prompt_tokens=100, output_tokens=50, cost_usd=0.25),
    )
    crashing = FakeLLM([PLAN, expensive_step, ProviderUnavailableError("gone")])
    with pytest.raises(ProviderUnavailableError):
        await build_runtime(crashing, tasks).run(task)
    await engine.dispose()

    engine = create_engine(database_url)
    tasks = SqliteTaskRepository(create_session_factory(engine))
    interrupted = await tasks.get(task.id)

    # What the first process spent is carried into the second, so a task that
    # crashes repeatedly still runs into its budget instead of round the clock.
    assert interrupted.cost_usd == pytest.approx(0.25)
    assert RunState.from_state(interrupted.execution.state).transcript.cost_usd == pytest.approx(
        0.25
    )

    cheap = replace(reply("hello"), usage=Usage(cost_usd=0.01))
    await build_runtime(FakeLLM([cheap, PASS]), tasks).run(interrupted)

    completed = await tasks.get(task.id)
    assert completed.cost_usd == pytest.approx(0.26)

    await engine.dispose()
