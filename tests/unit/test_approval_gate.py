"""The brake: which actions wait for a person, and what happens when nobody answers."""

from __future__ import annotations

import pytest

from application.employee_runtime.approvals import ApprovalGate
from domain.approvals.gate import RiskAssessment, assess_call, describe
from domain.approvals.models import ApprovalState
from domain.policies.models import Decision, RiskLevel
from domain.tasks.task import Task
from domain.tools.models import ToolResult, ToolSpec
from domain.tools.schema import Param
from tests.fakes.approvals import ScriptedApprovalService
from tests.fakes.employees import definition
from tests.fakes.tools import FakeTool


def spec(**kwargs) -> ToolSpec:
    return ToolSpec.of("fs.write", "Write a file.", Param("path"), **kwargs)


# --- The rule ------------------------------------------------------------------


def test_a_low_risk_action_just_happens() -> None:
    assert assess_call(spec()).decision is Decision.ALLOW


def test_a_high_risk_action_waits_for_a_person() -> None:
    assert assess_call(spec(risk_level=RiskLevel.HIGH)).decision is Decision.REQUIRE_APPROVAL


def test_an_irreversible_tool_always_waits_whatever_it_says_about_the_call() -> None:
    """Declaring a tool irreversible is the whole point; it cannot talk itself down."""
    decision = assess_call(
        spec(reversible=False), RiskAssessment(RiskLevel.LOW, "looks harmless")
    )

    assert decision.decision is Decision.REQUIRE_APPROVAL


def test_a_reversible_tool_knows_more_about_the_call_than_its_spec_does() -> None:
    declared = spec(risk_level=RiskLevel.MEDIUM)

    assert assess_call(declared, RiskAssessment(RiskLevel.HIGH, "would overwrite")).decision is (
        Decision.REQUIRE_APPROVAL
    )
    assert assess_call(declared, RiskAssessment(RiskLevel.LOW, "new file")).decision is (
        Decision.ALLOW
    )


def test_the_reason_shown_to_the_user_comes_from_the_tool() -> None:
    decision = assess_call(spec(), RiskAssessment(RiskLevel.HIGH, "Overwrite notes.txt"))
    assert decision.reason == "Overwrite notes.txt"


def test_a_long_argument_is_trimmed_before_it_is_shown() -> None:
    line = describe(spec(), {"path": "a.txt", "content": "x" * 500})
    assert len(line) < 300
    assert "..." in line


# --- The gate ------------------------------------------------------------------


class RiskyTool(FakeTool):
    """A tool that always says this call is dangerous."""

    def assess(self, input_data: dict) -> RiskAssessment:
        return RiskAssessment(RiskLevel.HIGH, "this would destroy something")


@pytest.fixture
def task() -> Task:
    return Task.create("Tidy the folder")


async def test_an_approved_action_proceeds(task: Task) -> None:
    service = ScriptedApprovalService.approving()
    tool = RiskyTool("fs.write", result=ToolResult.ok(written=True))

    outcome = await ApprovalGate(service).check(tool, {"path": "a"}, task, definition())

    assert outcome.allowed
    assert service.requests[0].task_id == task.id
    assert service.requests[0].risk_level is RiskLevel.HIGH


async def test_a_rejected_action_does_not_happen_and_says_why(task: Task) -> None:
    outcome = await ApprovalGate(ScriptedApprovalService.rejecting()).check(
        RiskyTool("fs.write"), {"path": "a"}, task, definition()
    )

    assert not outcome.allowed
    assert "did not approve" in outcome.reason


async def test_with_no_approver_configured_nothing_irreversible_happens(task: Task) -> None:
    """The default for an action nobody confirmed is not to do it."""
    outcome = await ApprovalGate(None).check(
        RiskyTool("fs.write"), {"path": "a"}, task, definition()
    )

    assert not outcome.allowed
    assert "no approver is configured" in outcome.reason


async def test_a_harmless_call_is_never_put_to_the_user(task: Task) -> None:
    service = ScriptedApprovalService.approving()

    outcome = await ApprovalGate(service).check(
        FakeTool("fs.read"), {"path": "a"}, task, definition()
    )

    assert outcome.allowed
    assert service.requests == [], "a question nobody needed to answer trains them to click yes"


async def test_the_stored_request_carries_no_credential(task: Task) -> None:
    service = ScriptedApprovalService.approving()

    await ApprovalGate(service).check(
        RiskyTool("api.send"), {"url": "https://x", "api_key": "sk-secret"}, task, definition()
    )

    assert service.requests[0].payload["api_key"] == "***"
    assert "sk-secret" not in str(service.requests[0].payload)


async def test_the_decision_records_who_asked(task: Task) -> None:
    service = ScriptedApprovalService.approving()
    employee = definition("organizer")

    await ApprovalGate(service).check(RiskyTool("fs.move"), {}, task, employee)

    assert service.requests[0].requested_by_employee_id == employee.id


def test_an_approval_carries_its_decision_and_when_it_was_made() -> None:
    from domain.approvals.models import Approval, ApprovalRequest

    approval = Approval(request=ApprovalRequest.create(Task.create("x").id, "fs.write(...)"))
    assert approval.is_pending

    resolved = approval.resolve(ApprovalState.APPROVED, comment="fine")

    assert resolved.state is ApprovalState.APPROVED
    assert resolved.resolved_at is not None
    assert resolved.id == approval.id
