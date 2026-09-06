"""Turning one objective into the tasks that will satisfy it.

This is not the employee planner. That one breaks a task into steps for a single
run; this one breaks an objective into *tasks*, each of which will be given to
somebody and executed in full. The unit of decomposition here costs an entire
employee run, which is why the prompt argues for fewer of them and why the
default assumption is one.

Three decisions are worth stating.

**A plan is a value, and replanning makes a new one.** Revisions supersede
rather than overwrite: what KAI thought the first time is the only evidence of
why a second attempt was needed, and an edited plan destroys it.

**Dependencies are declared, not implied by order.** A list of tasks in an order
somebody happened to write them in cannot be run in parallel and cannot be
checked for a cycle. Declared edges can be both, which is what makes Phase 12's
concurrency a change of executor rather than a change of plan.

**A plan that cannot be read is still a plan.** A model that returns prose gets
the objective back as a single task rather than an exception. One task that says
exactly what the user asked for is a worse plan than a good decomposition and a
far better outcome than a run that never started.
"""

from __future__ import annotations

from dataclasses import replace
from uuid import UUID, uuid4

import structlog

from application.kai.workforce import describe
from application.prompts import render
from domain.capabilities.models import CapabilityRequirement
from domain.employees.definition import EmployeeDefinition
from domain.llm.json_output import extract_object
from domain.llm.models import LLMRequest, Message, RoutingHints, TaskKind
from domain.llm.protocols import LLM
from domain.tasks.task import Task, TaskCreatedBy
from domain.workforce.protocols import Objective, Plan, PlanStatus

log = structlog.get_logger(__name__)

#: How many tasks one objective may become. Each is a whole employee run with
#: its own budget, so the ceiling is low on purpose.
MAX_TASKS = 6


class ObjectivePlanner:
    """Objective in, `Plan` out. Tasks are created here but not yet saved."""

    def __init__(self, llm: LLM, *, max_tasks: int = MAX_TASKS) -> None:
        self._llm = llm
        self._max_tasks = max_tasks

    async def plan(
        self,
        objective: Objective,
        workforce: list[EmployeeDefinition],
        *,
        restatement: str = "",
        revision: int = 1,
        feedback: tuple[str, ...] = (),
    ) -> Plan:
        prompt = render(
            "kai_planner",
            objective=objective.text,
            restatement=restatement or objective.text,
            constraints=_constraints(objective),
            criteria=_criteria(objective),
            workforce=describe(workforce),
            max_tasks=self._max_tasks,
            feedback=_feedback(feedback),
        )
        response = await self._llm.generate(
            LLMRequest(
                messages=(Message.user(prompt),),
                temperature=0.0,
                response_format={"type": "json_object"},
            )
        )

        parsed = extract_object(response.content) or {}
        # The plan's id is minted first so its tasks can carry it. A task that
        # does not know its plan cannot be found from one, and `tasks.plan_id`
        # would be a column nothing ever filled in.
        plan_id = uuid4()
        tasks, dependencies = self._read(parsed, objective, plan_id)
        if not tasks:
            log.warning("kai.plan_unreadable", objective_id=str(objective.id))
            tasks, dependencies = (self._task(objective, objective.text, plan_id),), ()

        plan = Plan(
            id=plan_id,
            objective_id=objective.id,
            tasks=tasks,
            dependencies=dependencies,
            revision=revision,
            status=PlanStatus.DRAFT,
            rationale=str(parsed.get("rationale", "")).strip(),
            workspace_id=objective.workspace_id,
        )
        log.info(
            "kai.planned",
            objective_id=str(objective.id),
            plan_id=str(plan.id),
            revision=revision,
            tasks=len(plan.tasks),
            dependencies=len(plan.dependencies),
        )
        return plan

    # --- Reading the model's answer -------------------------------------------

    def _read(
        self, parsed: dict[str, object], objective: Objective, plan_id: UUID
    ) -> tuple[tuple[Task, ...], tuple[tuple[UUID, UUID], ...]]:
        """Turn the model's task ids into real ones, dropping what cannot be used."""
        raw = parsed.get("tasks")
        if not isinstance(raw, list | tuple):
            return (), ()

        tasks: dict[str, Task] = {}
        for index, item in enumerate(raw):
            if not isinstance(item, dict):
                continue
            goal = str(item.get("goal", "")).strip()
            if not goal:
                continue
            key = str(item.get("id", "") or f"t{index + 1}")
            tasks[key] = self._task(objective, goal, plan_id, priority=5 - min(index, 4))
            if len(tasks) == self._max_tasks:
                break

        dependencies: list[tuple[UUID, UUID]] = []
        for index, item in enumerate(raw[: len(tasks)]):
            if not isinstance(item, dict):
                continue
            key = str(item.get("id", "") or f"t{index + 1}")
            if key not in tasks:
                continue
            for other in item.get("depends_on") or ():
                # An edge to a task that was dropped, or to itself, is not a
                # dependency - it is a task that could never become ready.
                if str(other) in tasks and str(other) != key:
                    dependencies.append((tasks[key].id, tasks[str(other)].id))

        return tuple(tasks.values()), tuple(dependencies)

    @staticmethod
    def _task(objective: Objective, goal: str, plan_id: UUID, *, priority: int = 5) -> Task:
        return replace(
            Task.create(
                goal,
                workspace_id=objective.workspace_id,
                created_by=TaskCreatedBy.KAI,
                priority=priority,
            ),
            plan_id=plan_id,
        )

    @staticmethod
    def routing() -> tuple[TaskKind, CapabilityRequirement, RoutingHints]:
        """Decomposition happens once per objective and decides everything after it."""
        return (
            TaskKind.PLANNING,
            CapabilityRequirement(),
            RoutingHints(quality=0.8, cost_sensitivity=0.3),
        )


def _constraints(objective: Objective) -> str:
    if not objective.constraints:
        return "none stated"
    return "; ".join(f"{key}: {value}" for key, value in sorted(objective.constraints.items()))


def _criteria(objective: Objective) -> str:
    if not objective.acceptance_criteria:
        return "not stated - use your judgement about what the request needs"
    return "\n".join(f"- {item}" for item in objective.acceptance_criteria)


def _feedback(feedback: tuple[str, ...]) -> str:
    """What the last attempt failed on. Absent on the first attempt, by design."""
    if not feedback:
        return ""
    return (
        "# A previous plan did not satisfy the objective\n\n"
        "These are still missing. Plan for them:\n"
        + "\n".join(f"- {item}" for item in feedback)
    )
