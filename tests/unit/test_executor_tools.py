"""The tool path through the executor: permission, approval, accounting."""

from __future__ import annotations

from application.employee_runtime.approvals import ApprovalGate
from application.employee_runtime.executor import Executor
from application.employee_runtime.transcript import Transcript
from domain.approvals.gate import RiskAssessment
from domain.llm.models import ToolCallRequest
from domain.policies.models import RiskLevel
from domain.tasks.task import Task
from domain.tools.models import ToolResult
from infrastructure.persistence.tool_call_repository import InMemoryToolCallLog
from infrastructure.tools.registry import InMemoryToolRegistry
from tests.fakes.approvals import ScriptedApprovalService
from tests.fakes.employees import definition
from tests.fakes.llm import FakeLLM, reply, tool_reply
from tests.fakes.tools import FakeTool


class DangerousTool(FakeTool):
    def assess(self, input_data: dict) -> RiskAssessment:
        return RiskAssessment(RiskLevel.HIGH, "would overwrite notes.txt")


def opening(task: Task, employee) -> Transcript:
    return Transcript(messages=Executor.opening_messages(task, employee, None, "be useful"))


def one_call(name: str, **arguments) -> FakeLLM:
    return FakeLLM(
        [
            tool_reply(ToolCallRequest(id="c1", name=name, arguments=arguments)),
            reply("Done."),
        ]
    )


async def test_an_approved_call_reaches_the_tool() -> None:
    task, employee = Task.create("Write it"), definition(tools=frozenset({"fs.write"}))
    tool = DangerousTool("fs.write", result=ToolResult.ok(written=True))

    await Executor(
        one_call("fs.write", path="notes.txt"),
        InMemoryToolRegistry([tool]),
        approvals=ApprovalGate(ScriptedApprovalService.approving()),
    ).run(task, employee, opening(task, employee))

    assert tool.calls == [{"path": "notes.txt"}]


async def test_a_rejected_call_never_reaches_the_tool() -> None:
    """The DoD of this phase: an irreversible action without a yes cannot happen."""
    task, employee = Task.create("Write it"), definition(tools=frozenset({"fs.write"}))
    tool = DangerousTool("fs.write")

    outcome = await Executor(
        one_call("fs.write", path="notes.txt"),
        InMemoryToolRegistry([tool]),
        approvals=ApprovalGate(ScriptedApprovalService.rejecting()),
    ).run(task, employee, opening(task, employee))

    assert tool.calls == []
    assert "did not approve" in outcome.transcript.observations[0].summary


async def test_without_an_approval_service_a_dangerous_call_is_refused() -> None:
    task, employee = Task.create("Write it"), definition(tools=frozenset({"fs.write"}))
    tool = DangerousTool("fs.write")

    await Executor(
        one_call("fs.write", path="notes.txt"), InMemoryToolRegistry([tool])
    ).run(task, employee, opening(task, employee))

    assert tool.calls == []


async def test_a_tool_the_employee_does_not_have_is_never_put_to_the_user() -> None:
    """Permission is checked before approval: refusing costs nothing, asking costs a person."""
    task, employee = Task.create("Write it"), definition(tools=frozenset({"fs.read"}))
    service = ScriptedApprovalService.approving()

    outcome = await Executor(
        one_call("fs.write", path="notes.txt"),
        InMemoryToolRegistry([DangerousTool("fs.write")]),
        approvals=ApprovalGate(service),
    ).run(task, employee, opening(task, employee))

    assert service.requests == []
    assert "may not use" in outcome.transcript.observations[0].summary


async def test_every_call_is_accounted_for() -> None:
    task, employee = Task.create("Read it"), definition(tools=frozenset({"fs.read"}))
    log = InMemoryToolCallLog()

    await Executor(
        one_call("fs.read", path="a.txt"),
        InMemoryToolRegistry([FakeTool("fs.read", result=ToolResult.ok(text="hi"))]),
        call_log=log,
    ).run(task, employee, opening(task, employee))

    recorded = await log.list_for_task(task.id)
    assert [call.tool for call in recorded] == ["fs.read"]
    assert recorded[0].success


async def test_a_refused_call_is_recorded_too() -> None:
    # Otherwise the trace shows an employee that simply stopped, with no reason.
    task, employee = Task.create("Write it"), definition(tools=frozenset({"fs.write"}))
    log = InMemoryToolCallLog()

    await Executor(
        one_call("fs.write", path="notes.txt"),
        InMemoryToolRegistry([DangerousTool("fs.write")]),
        approvals=ApprovalGate(ScriptedApprovalService.rejecting()),
        call_log=log,
    ).run(task, employee, opening(task, employee))

    recorded = await log.list_for_task(task.id)
    assert [(call.tool, call.success) for call in recorded] == [("fs.write", False)]


async def test_a_credential_in_an_argument_never_enters_the_transcript() -> None:
    """The transcript is persisted and sent back to the model on the next step."""
    task, employee = Task.create("Send it"), definition(tools=frozenset({"api.send"}))
    log = InMemoryToolCallLog()

    outcome = await Executor(
        one_call("api.send", url="https://x", api_key="sk-live-secret"),
        InMemoryToolRegistry([FakeTool("api.send", result=ToolResult.ok(token="t-1"))]),
        call_log=log,
    ).run(task, employee, opening(task, employee))

    observation = outcome.transcript.observations[0]
    assert "sk-live-secret" not in str(observation.to_dict())
    assert observation.details["arguments"]["api_key"] == "***"
    assert "sk-live-secret" not in str((await log.list_for_task(task.id))[0].input_data)


async def test_a_broken_telemetry_log_does_not_fail_the_task() -> None:
    class BrokenLog:
        async def record(self, call) -> None:
            raise RuntimeError("disk is full")

        async def list_for_task(self, task_id):  # pragma: no cover - never reached
            return []

    task, employee = Task.create("Read it"), definition(tools=frozenset({"fs.read"}))

    outcome = await Executor(
        one_call("fs.read", path="a.txt"),
        InMemoryToolRegistry([FakeTool("fs.read")]),
        call_log=BrokenLog(),
    ).run(task, employee, opening(task, employee))

    assert outcome.finished
