"""Reading what was actually asked for, and whether it needs the workforce.

Two questions, answered from one reading, because they come apart badly. §7.3
asks for free text to become an `Objective` with constraints and acceptance
criteria; §7.5 asks KAI to do simple things directly rather than decompose them
on principle. Both are the same act of comprehension, and splitting them into
two model calls means the second one re-reads what the first already understood.

The user's sentence is never replaced. What KAI understood is recorded *beside*
it, so a misreading stays visible next to the thing it misread instead of
quietly becoming the objective.

An unreadable answer is not a failure here. A request that could not be parsed
into constraints is still a request, and treating it as work to be planned is a
better outcome than refusing to start - so the fallback is the plainest possible
reading: do what they said, criteria unstated.
"""

from __future__ import annotations

import structlog

from application.kai.workforce import describe
from application.prompts import render
from domain.capabilities.models import CapabilityRequirement
from domain.employees.definition import EmployeeDefinition
from domain.llm.json_output import extract_object
from domain.llm.models import LLMRequest, Message, RoutingHints, TaskKind
from domain.llm.protocols import LLM
from domain.workforce.intent import Intent

log = structlog.get_logger(__name__)


class IntentReader:
    """Free text in, `Intent` out."""

    def __init__(self, llm: LLM) -> None:
        self._llm = llm

    async def read(self, request: str, workforce: list[EmployeeDefinition]) -> Intent:
        prompt = render("kai_intent", request=request, workforce=describe(workforce))
        response = await self._llm.generate(
            LLMRequest(
                messages=(Message.user(prompt),),
                temperature=0.0,
                response_format={"type": "json_object"},
            )
        )

        parsed = extract_object(response.content)
        if parsed is None:
            log.warning("kai.intent_unreadable", reply=response.content[:200])
            return Intent(restatement=request, needs_work=True)

        needs_work = bool(parsed.get("needs_work", True))
        answer = str(parsed.get("answer", "")).strip()
        # A model that says "no work needed" and then supplies no answer has
        # told us nothing. The safe reading of that is that there is work.
        if not needs_work and not answer:
            log.info("kai.intent_answerless", restatement=parsed.get("restatement", ""))
            needs_work = True

        intent = Intent(
            restatement=str(parsed.get("restatement", "")).strip() or request,
            constraints=_as_mapping(parsed.get("constraints")),
            acceptance_criteria=_as_criteria(parsed.get("acceptance_criteria")),
            needs_work=needs_work,
            answer="" if needs_work else answer,
        )
        log.info(
            "kai.intent_read",
            needs_work=intent.needs_work,
            criteria=len(intent.acceptance_criteria),
            constraints=sorted(intent.constraints),
        )
        return intent

    @staticmethod
    def routing() -> tuple[TaskKind, CapabilityRequirement, RoutingHints]:
        """Comprehension is the one thing here that must not be cheap.

        Everything downstream is built on this reading; a constraint dropped
        here is a constraint nothing later can recover.
        """
        return (
            TaskKind.EXTRACTION,
            CapabilityRequirement(),
            RoutingHints(quality=0.8, cost_sensitivity=0.3),
        )


def _as_mapping(raw: object) -> dict[str, object]:
    return {str(key): value for key, value in raw.items()} if isinstance(raw, dict) else {}


def _as_criteria(raw: object) -> tuple[str, ...]:
    if not isinstance(raw, list | tuple):
        return ()
    return tuple(str(item).strip() for item in raw if str(item).strip())
