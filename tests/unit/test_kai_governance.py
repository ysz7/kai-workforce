"""The rules KAI is not allowed to break (Phase 7, §7.13).

These are the tests the phase exists to make possible. A manager that can hand
out a tool nobody was trusted with, or approve its own work, is not a manager -
it is a hole in every guarantee the phases below it established.
"""

from __future__ import annotations

import ast
from pathlib import Path
from uuid import uuid4

from application.employee_runtime.executor import Executor
from application.employee_runtime.runtime import EmployeeRuntime, RuntimeDependencies
from application.kai.delegation import CapabilityDelegator, manager_actor
from domain.policies.models import ActorKind, effective_tools
from domain.tasks.plan import TaskPlan
from domain.tasks.task import Task
from domain.workforce.assignment import SharedContext, TaskAssignment
from infrastructure.persistence.in_memory_task_repository import InMemoryTaskRepository
from infrastructure.tools.registry import InMemoryToolRegistry
from tests.fakes.employees import definition
from tests.fakes.llm import FakeLLM, reply
from tests.fakes.tools import FakeTool
from tests.fakes.workforce import FakeRegistry

REPO_ROOT = Path(__file__).resolve().parents[2]
KAI_DIR = REPO_ROOT / "application" / "kai"


# --- No employee is named in KAI's code (§7.6, and the phase's DoD) ------------


def test_kai_never_names_a_declared_employee() -> None:
    """The DoD in one assertion.

    Every employee under `employees/` is found by reading the directory, so this
    keeps working as employees are added - which is the point: adding one must
    never mean editing KAI.
    """
    declared = sorted(
        path.parent.name for path in (REPO_ROOT / "employees").glob("*/employee.yaml")
    )
    assert declared, "the check is worthless if it finds no employees to look for"

    offenders: dict[str, list[str]] = {}
    for path in sorted(KAI_DIR.rglob("*.py")):
        text = path.read_text(encoding="utf-8").lower()
        found = [name for name in declared if name in text]
        if found:
            offenders[str(path.relative_to(REPO_ROOT))] = found
    assert not offenders, f"KAI names a concrete employee: {offenders}"


def test_kai_reaches_the_workforce_only_through_the_registry() -> None:
    """No file access, no YAML, no directory walk, and no runtime.

    The runtime one matters as much as the rest: KAI holds `TaskExecution`, a
    contract, so the whole manager can be exercised against a stand-in that
    never calls a model - which is what every test in this directory does.
    """
    forbidden = {"yaml", "pathlib", "os", "glob", "sqlalchemy", "httpx"}
    offenders: dict[str, list[str]] = {}
    for path in sorted(KAI_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
        found = sorted(roots & forbidden)
        # `application.task_runner` is in KAI's own layer, so the layering
        # contract would allow it. Depending on it would still put the runtime
        # inside the manager, which is exactly what the protocol exists to keep
        # out - so it is named here rather than left to import-linter.
        text = path.read_text(encoding="utf-8")
        if "application.task_runner" in text or "employee_runtime" in text:
            found.append("the employee runtime")
        if found:
            offenders[str(path.relative_to(REPO_ROOT))] = found
    assert not offenders, f"KAI reached around its contracts: {offenders}"


# --- Delegation never escalates privileges (§7.13) ----------------------------


async def test_kai_cannot_grant_a_tool_the_employee_does_not_have() -> None:
    narrow = definition("narrow", tools=frozenset({"fs.read"}))
    wide = definition("wide", tools=frozenset({"fs.read", "fs.write", "web.search"}))
    delegator = CapabilityDelegator(
        FakeLLM([reply('{"employee": "narrow", "reason": "it reads"}')]),
        FakeRegistry(narrow, wide),
    )

    chosen, context, _ = await delegator.choose(Task.create("Read the file"))

    assert chosen.name == "narrow"
    granted = set(context.data["granted_tools"])
    assert granted == {"fs.read"}, "the manager may hand down only what this employee has"
    assert "web.search" not in granted, "another employee's tool is not this one's to receive"


def test_the_manager_actor_can_never_exceed_the_union_of_the_workforce() -> None:
    first = definition("first", tools=frozenset({"fs.read"}))
    second = definition("second", tools=frozenset({"web.search"}))

    kai = manager_actor([first, second])

    assert kai.actor_kind is ActorKind.KAI
    assert kai.allowed_tools == frozenset({"fs.read", "web.search"})
    assert "*" not in kai.allowed_tools, "a wildcard would make the intersection meaningless"
    # And the intersection with any one employee is that employee's own rights.
    assert effective_tools(kai, first) == first.allowed_tools
    assert effective_tools(kai, second) == second.allowed_tools


def test_an_empty_workforce_grants_nothing() -> None:
    assert manager_actor([]).allowed_tools == frozenset()


async def test_an_assignment_can_narrow_what_an_employee_may_use() -> None:
    """Narrowing works, which is what makes the intersection more than a no-op."""
    employee = definition("worker", tools=frozenset({"fs.read", "fs.write"}))
    seen: list[list[str]] = []

    class Watcher:
        async def run(self, task, definition_, transcript, *, on_step=None):
            seen.append(sorted(spec.name for spec in registry.list_specs(definition_)))
            from application.employee_runtime.executor import StepOutcome

            return StepOutcome(transcript=transcript, finished=True, answer="done")

    registry = InMemoryToolRegistry([FakeTool("fs.read"), FakeTool("fs.write")])
    tasks = InMemoryTaskRepository()
    task = Task.create("Read something")
    await tasks.save(task)

    class StubPlanner:
        async def plan(self, *args, **kwargs):
            return TaskPlan.of("Read it")

    class PassingVerifier:
        async def verify(self, *args, **kwargs):
            from domain.employees.verification import Verdict

            return Verdict.ok("fine")

    runtime = EmployeeRuntime(
        employee,
        RuntimeDependencies(
            planner=StubPlanner(),  # type: ignore[arg-type]
            executor=Watcher(),  # type: ignore[arg-type]
            verifier=PassingVerifier(),  # type: ignore[arg-type]
            tasks=tasks,
            tools=registry,
            limits=employee.limits,
        ),
    )

    await runtime.run(
        task,
        TaskAssignment.create(
            task_id=task.id,
            employee_id=employee.id,
            assigned_by=ActorKind.KAI,
            context=SharedContext(data={"granted_tools": ["fs.read"]}),
        ),
    )

    assert seen == [["fs.read"]], "the withheld tool was not offered to the model"


async def test_an_assignment_cannot_widen_what_an_employee_may_use() -> None:
    """The same mechanism, pointed the other way: it only ever intersects."""
    employee = definition("worker", tools=frozenset({"fs.read"}))
    runtime = EmployeeRuntime(employee, RuntimeDependencies(
        planner=None,  # type: ignore[arg-type]
        executor=Executor(FakeLLM(), InMemoryToolRegistry()),
        verifier=None,  # type: ignore[arg-type]
        tasks=InMemoryTaskRepository(),
        tools=InMemoryToolRegistry(),
        limits=employee.limits,
    ))

    effective = runtime._effective(
        TaskAssignment.create(
            task_id=uuid4(),
            employee_id=employee.id,
            assigned_by=ActorKind.KAI,
            context=SharedContext(data={"granted_tools": ["fs.read", "fs.write", "code.run"]}),
        )
    )

    assert effective.allowed_tools == frozenset({"fs.read"})


# --- KAI never approves its own work (§7.10) ----------------------------------


def test_kai_never_resolves_an_approval() -> None:
    """Asking is the manager's; answering is a person's.

    Checked as a property of the source rather than of one run: an approval KAI
    could resolve is an approval that has stopped meaning anything, and it would
    not show up as a failing assertion anywhere else.
    """
    offenders: dict[str, list[str]] = {}
    for path in sorted(KAI_DIR.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        found = [
            token
            for token in ("ApprovalService", "approval_service", ".resolve(", "ApprovalState")
            if token in text
        ]
        if found:
            offenders[str(path.relative_to(REPO_ROOT))] = found
    assert not offenders, f"KAI touched the approval machinery: {offenders}"


async def test_a_delegated_task_still_stops_at_the_gate() -> None:
    """Delegation changes who asked, not whether the gate applies.

    An irreversible action inside a task KAI handed out is refused exactly as it
    would have been had the user given the task to that employee directly.
    """
    from application.employee_runtime.approvals import ApprovalGate
    from application.employee_runtime.transcript import Transcript
    from domain.llm.models import ToolCallRequest
    from domain.policies.models import RiskLevel
    from domain.tools.models import ToolSpec
    from tests.fakes.approvals import ScriptedApprovalService
    from tests.fakes.llm import tool_reply

    class Irreversible(FakeTool):
        def __init__(self) -> None:
            super().__init__("fs.write")
            self._spec = ToolSpec(
                name="fs.write",
                description="Overwrite a file.",
                json_schema={"type": "object", "properties": {}},
                risk_level=RiskLevel.HIGH,
                reversible=False,
            )

    employee = definition("worker", tools=frozenset({"fs.write"}))
    tool = Irreversible()
    approvals = ScriptedApprovalService.rejecting()
    llm = FakeLLM(
        [
            tool_reply(ToolCallRequest(id="c1", name="fs.write", arguments={"path": "a"})),
            reply("I was not allowed to."),
        ]
    )
    executor = Executor(
        llm,
        InMemoryToolRegistry([tool]),
        approvals=ApprovalGate(approvals),
    )
    task = Task.create("Overwrite it")

    outcome = await executor.run(task, employee, Transcript())

    assert tool.calls == [], "the irreversible action never ran"
    assert len(approvals.requests) == 1
    assert approvals.requests[0].task_id == task.id
    assert outcome.transcript.observations[0].succeeded is False
