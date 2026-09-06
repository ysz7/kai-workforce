"""Turns a task into a plan of steps.

The plan is not the work. It exists so the executor has something to check
itself against, and so a human reading the trace afterwards can see what the
employee thought it was doing.
"""

from __future__ import annotations

import structlog

from application.prompts import render
from domain.capabilities.models import CapabilityRequirement
from domain.employees.definition import EmployeeDefinition
from domain.errors import PlanningError
from domain.llm.json_output import extract_object
from domain.llm.models import LLMRequest, Message, RoutingHints, TaskKind
from domain.llm.protocols import LLM
from domain.tasks.plan import PlanStep, TaskPlan
from domain.tasks.task import Task
from domain.tools.models import ToolSpec
from domain.workforce.assignment import SharedContext

# structlog is a library, like json. Configuring it is the composition root's
# job; using it here would only be a layering problem if this reached into
# `infrastructure/` to do it.
log = structlog.get_logger(__name__)

MAX_PLAN_STEPS = 8


class Planner:
    """Implements `domain.employees.protocols.Planner`."""

    def __init__(self, llm: LLM, *, max_steps: int = MAX_PLAN_STEPS) -> None:
        self._llm = llm
        self._max_steps = max_steps

    async def plan(
        self,
        task: Task,
        definition: EmployeeDefinition,
        tools: list[ToolSpec] | None = None,
        context: SharedContext | None = None,
    ) -> TaskPlan:
        prompt = render(
            "planner",
            role=definition.role.title,
            role_description=definition.role.description,
            goals="\n".join(f"- {goal.text}" for goal in definition.goals) or "- none stated",
            goal=task.goal,
            context=_context_block(context),
            max_steps=self._max_steps,
            tools=", ".join(spec.name for spec in tools or ()) or "none",
        )

        response = await self._llm.generate(
            LLMRequest(
                messages=(Message.user(prompt),),
                temperature=0.0,
                response_format={"type": "json_object"},
            )
        )

        parsed = extract_object(response.content)
        if parsed is None:
            raise PlanningError(
                f"The planner returned no usable JSON: {response.content[:200]!r}"
            )

        steps = tuple(
            PlanStep(
                index=index,
                description=str(step.get("description", "")).strip(),
                expected_outcome=str(step.get("expected_outcome", "")).strip(),
            )
            for index, step in enumerate(parsed.get("steps", ()))
            if isinstance(step, dict) and str(step.get("description", "")).strip()
        )
        if not steps:
            raise PlanningError("The planner produced a plan with no steps")

        plan = TaskPlan(steps=steps[: self._max_steps], rationale=str(parsed.get("rationale", "")))
        log.info("task.planned", task_id=str(task.id), steps=len(plan.steps))
        return plan

    @staticmethod
    def routing() -> tuple[TaskKind, CapabilityRequirement, RoutingHints]:
        """Planning wants judgement, and it happens once per task."""
        return (
            TaskKind.PLANNING,
            CapabilityRequirement(),
            RoutingHints(quality=0.8, cost_sensitivity=0.3),
        )


def _context_block(context: SharedContext | None) -> str:
    if context is None:
        return ""
    parts: list[str] = []
    if context.facts:
        parts.append("# What you were told\n" + "\n".join(f"- {f}" for f in context.facts))
    if context.constraints:
        parts.append("# Constraints\n" + "\n".join(f"- {c}" for c in context.constraints))
    return "\n\n".join(parts)
