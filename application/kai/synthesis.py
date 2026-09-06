"""One answer, from however many reports it took.

The user asked KAI, not the team, and has not seen the plan. Handing back a list
of task summaries would make them do the manager's job - reading four reports to
find the one sentence they wanted.

The rule that matters is what synthesis must *not* lose: names, numbers, links
and paths. A summary that drops the specifics is worse than the reports it
replaced, because the reports at least had them. So the prompt says so, and the
fallback below - used when a model call is unavailable or produces nothing -
keeps the reports intact rather than inventing a smoother answer than the
evidence supports.

A shortfall is stated, never smoothed. An objective that came up short and reads
as though it did not is the one failure mode of this component that a user
cannot detect for themselves.
"""

from __future__ import annotations

import structlog

from application.kai.supervisor import TaskOutcome
from application.prompts import render
from domain.capabilities.models import CapabilityRequirement
from domain.llm.models import LLMRequest, Message, RoutingHints, TaskKind
from domain.llm.protocols import LLM
from domain.workforce.protocols import Objective

log = structlog.get_logger(__name__)


class Synthesizer:
    """Turns what the team produced into what the user reads."""

    def __init__(self, llm: LLM) -> None:
        self._llm = llm

    async def synthesize(
        self,
        objective: Objective,
        outcomes: tuple[TaskOutcome, ...],
        *,
        missing: tuple[str, ...] = (),
    ) -> str:
        results = describe(outcomes)
        if not results.strip():
            return "Nothing was produced for this objective."

        response = await self._llm.generate(
            LLMRequest(
                messages=(
                    Message.user(
                        render(
                            "kai_synthesis",
                            objective=objective.text,
                            criteria=_criteria(objective),
                            results=results,
                            shortfall=_shortfall(missing),
                        )
                    ),
                ),
                temperature=0.2,
            )
        )
        answer = response.content.strip()
        if not answer:
            # Better the raw reports than a blank page: the work happened, and
            # the user is entitled to it even when the last call said nothing.
            log.warning("kai.synthesis_empty", objective_id=str(objective.id))
            return results
        return answer

    @staticmethod
    def routing() -> tuple[TaskKind, CapabilityRequirement, RoutingHints]:
        """The only text the user actually reads. Worth a good model."""
        return (
            TaskKind.SYNTHESIS,
            CapabilityRequirement(),
            RoutingHints(quality=0.8, cost_sensitivity=0.4),
        )


def describe(outcomes: tuple[TaskOutcome, ...]) -> str:
    """What came back, task by task - the input to synthesis and to verification.

    Failures are included, not filtered. A checker shown only the successes is
    being asked whether the parts that worked worked.
    """
    blocks: list[str] = []
    for outcome in outcomes:
        summary = (
            outcome.task.result.summary.strip()
            if outcome.task.result and outcome.task.result.summary.strip()
            else outcome.reason or "produced nothing"
        )
        header = f"## {outcome.task.goal}"
        status = "" if outcome.succeeded else f" [{outcome.task.status.value}]"
        blocks.append(f"{header}{status}\nDone by: {outcome.employee or 'nobody'}\n{summary}")
        artifacts = outcome.task.result.artifacts if outcome.task.result else ()
        if artifacts:
            blocks.append("Files: " + ", ".join(artifacts))
    return "\n\n".join(blocks)


def _criteria(objective: Objective) -> str:
    if not objective.acceptance_criteria:
        return "not stated"
    return "\n".join(f"- {item}" for item in objective.acceptance_criteria)


def _shortfall(missing: tuple[str, ...]) -> str:
    if not missing:
        return ""
    return "# What is still missing\n\n" + "\n".join(f"- {item}" for item in missing)
