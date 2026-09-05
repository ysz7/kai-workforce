"""Checks the result against the task. Never assumes success.

The employee that did the work is the wrong witness to whether it worked: a
confident summary is exactly what a failed run also produces. So a separate call
judges the output against the goal, and a task cannot complete without it.
"""

from __future__ import annotations

import structlog

from application.employee_runtime.prompts import render
from domain.capabilities.models import CapabilityRequirement
from domain.employees.verification import Verdict
from domain.llm.json_output import extract_object
from domain.llm.models import LLMRequest, Message, RoutingHints, TaskKind
from domain.llm.protocols import LLM
from domain.tasks.plan import TaskPlan
from domain.tasks.task import Task, TaskResult

log = structlog.get_logger(__name__)


class Verifier:
    """Implements `domain.employees.protocols.Verifier`."""

    def __init__(self, llm: LLM) -> None:
        self._llm = llm

    async def verify(
        self, task: Task, result: TaskResult, plan: TaskPlan | None = None
    ) -> Verdict:
        if not result.summary.strip():
            # No model call needed to know that nothing is not an answer.
            return Verdict.rejected("The task produced no output", "any result at all")

        prompt = render(
            "verifier",
            goal=task.goal,
            expected=_expected(plan),
            result=result.summary,
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
            # A verifier that cannot be read must not wave the work through.
            log.warning("task.verdict_unreadable", task_id=str(task.id))
            return Verdict.rejected(
                "The verifier did not return a readable verdict", "a second opinion"
            )

        passed = bool(parsed.get("passed", False))
        verdict = Verdict(
            passed=passed,
            reason=str(parsed.get("reason", "")).strip(),
            missing=tuple(
                str(item).strip() for item in parsed.get("missing", ()) if str(item).strip()
            ),
        )
        log.info(
            "task.verified", task_id=str(task.id), passed=verdict.passed, reason=verdict.reason
        )
        return verdict

    @staticmethod
    def routing() -> tuple[TaskKind, CapabilityRequirement, RoutingHints]:
        """Verification is a judgement about text, and it happens once."""
        return (
            TaskKind.VERIFICATION,
            CapabilityRequirement(),
            RoutingHints(quality=0.6, cost_sensitivity=0.7),
        )


def _expected(plan: TaskPlan | None) -> str:
    if plan is None or plan.is_empty:
        return "No plan was recorded; judge the result against the task itself."
    lines = [
        f"{step.index + 1}. {step.description}"
        + (f" -> {step.expected_outcome}" if step.expected_outcome else "")
        for step in plan.steps
    ]
    return "\n".join(lines)
