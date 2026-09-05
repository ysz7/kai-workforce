"""The three stages, and what happens between them."""

from __future__ import annotations

from application.employee_runtime.executor import Executor
from application.employee_runtime.planner import Planner
from application.employee_runtime.runtime import EmployeeRuntime, RuntimeDependencies
from application.employee_runtime.verifier import Verifier
from domain.employees.limits import ExecutionLimits
from domain.tasks.task import Task, TaskStatus
from infrastructure.persistence.in_memory_task_repository import InMemoryTaskRepository
from infrastructure.tools.registry import InMemoryToolRegistry
from tests.fakes.employees import definition
from tests.fakes.llm import FakeLLM, reply

PLAN = reply('{"steps": [{"description": "Answer it", "expected_outcome": "an answer"}]}')
PASS = reply('{"passed": true, "reason": "good enough"}')


def build(script, *, limits=None, tools=None):
    """One FakeLLM plays every stage; the script is the whole run in order."""
    llm = FakeLLM(script)
    registry = InMemoryToolRegistry(tools or [])
    tasks = InMemoryTaskRepository()
    employee = definition(limits=limits)
    deps = RuntimeDependencies(
        planner=Planner(llm),
        executor=Executor(llm, registry, limits=limits or ExecutionLimits()),
        verifier=Verifier(llm),
        tasks=tasks,
        tools=registry,
        limits=limits or ExecutionLimits(),
        system_prompt="You are a test employee.",
    )
    return EmployeeRuntime(employee, deps), tasks, llm


async def test_a_task_goes_plan_execute_verify_and_completes() -> None:
    runtime, tasks, _ = build([PLAN, reply("WAL lets readers and writers proceed."), PASS])
    task = Task.create("Explain WAL mode")
    await tasks.save(task)

    await runtime.run(task)

    stored = await tasks.get(task.id)
    assert stored.status is TaskStatus.COMPLETED
    assert "WAL" in stored.result.summary
    assert stored.plan is not None and len(stored.plan.steps) == 1


async def test_every_stage_transition_is_recorded() -> None:
    runtime, tasks, _ = build([PLAN, reply("An answer."), PASS])
    task = Task.create("Explain WAL mode")
    await tasks.save(task)

    await runtime.run(task)

    seen = [event.to_status for event in await tasks.events(task.id)]
    assert seen == [
        TaskStatus.PLANNING,
        TaskStatus.RUNNING,
        TaskStatus.VERIFYING,
        TaskStatus.COMPLETED,
    ]


async def test_a_retry_goes_back_through_planning_not_straight_to_work() -> None:
    reject = reply('{"passed": false, "reason": "no sources", "missing": ["sources"]}')
    runtime, tasks, _ = build(
        [PLAN, reply("It is faster."), reject, PLAN, reply("Per [1], faster."), PASS]
    )
    task = Task.create("Explain WAL mode")
    await tasks.save(task)

    await runtime.run(task)

    seen = [event.to_status for event in await tasks.events(task.id)]
    assert seen == [
        TaskStatus.PLANNING,
        TaskStatus.RUNNING,
        TaskStatus.VERIFYING,
        TaskStatus.PLANNING,
        TaskStatus.RUNNING,
        TaskStatus.VERIFYING,
        TaskStatus.COMPLETED,
    ]


async def test_a_rejected_result_is_retried_once_with_the_feedback() -> None:
    reject = reply('{"passed": false, "reason": "no sources", "missing": ["named sources"]}')
    runtime, tasks, llm = build(
        [PLAN, reply("It is faster."), reject, PLAN, reply("It is faster, per [1]."), PASS]
    )
    task = Task.create("Explain WAL mode")
    await tasks.save(task)

    await runtime.run(task)

    stored = await tasks.get(task.id)
    assert stored.status is TaskStatus.COMPLETED
    # The second attempt was told what the first one lacked.
    second_execution = llm.requests[4]
    assert "named sources" in second_execution.messages[1].content


async def test_a_second_rejection_fails_the_task_rather_than_looping() -> None:
    reject = reply('{"passed": false, "reason": "still no sources", "missing": ["sources"]}')
    runtime, tasks, _ = build(
        [PLAN, reply("It is faster."), reject, PLAN, reply("Still faster."), reject]
    )
    task = Task.create("Explain WAL mode")
    await tasks.save(task)

    await runtime.run(task)

    stored = await tasks.get(task.id)
    assert stored.status is TaskStatus.FAILED
    assert stored.error.kind == "VerificationFailed"
    assert stored.error.details["missing"] == ["sources"]
    # The work is still there to read, even though it did not pass.
    assert stored.result.summary == "Still faster."


async def test_a_failed_plan_does_not_stop_the_task_from_being_attempted() -> None:
    # No plan is worse than a plan, but much better than refusing to start.
    runtime, tasks, _ = build([reply("I refuse to plan."), reply("An answer anyway."), PASS])
    task = Task.create("Explain WAL mode")
    await tasks.save(task)

    await runtime.run(task)

    stored = await tasks.get(task.id)
    assert stored.status is TaskStatus.COMPLETED
    assert "Planning failed" in stored.plan.rationale


async def test_a_run_stopped_by_a_budget_is_not_retried() -> None:
    from dataclasses import replace as replace_field

    from domain.llm.models import ToolCallRequest
    from tests.fakes.llm import tool_reply
    from tests.fakes.tools import FakeTool

    reject = reply('{"passed": false, "reason": "incomplete", "missing": ["everything"]}')
    looping = replace_field(
        tool_reply(ToolCallRequest(id="c1", name="fs.read", arguments={})),
        content="partial",
    )
    runtime, tasks, _ = build(
        [PLAN, looping, looping, reject],
        limits=ExecutionLimits(max_steps=2),
        tools=[FakeTool("fs.read")],
    )
    task = Task.create("Loop forever")
    await tasks.save(task)

    await runtime.run(task)

    stored = await tasks.get(task.id)
    assert stored.status is TaskStatus.FAILED
    # Retrying a run that ran out of budget just spends the budget again.
    assert "steps limit" in stored.error.message


async def test_the_employee_prompt_and_goals_reach_the_model() -> None:
    runtime, tasks, llm = build([PLAN, reply("An answer."), PASS])
    task = Task.create("Explain WAL mode")
    await tasks.save(task)

    await runtime.run(task)

    system = llm.requests[1].messages[0].content
    assert "You are a test employee." in system
    assert "Answer the question that was asked." in system
