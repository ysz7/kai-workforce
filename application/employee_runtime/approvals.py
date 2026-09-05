"""The brake that comes with the hands.

Phase 4 is the phase where an employee stops reasoning and starts doing, and
the rule that arrives with it is short: an action the user cannot undo does not
happen until the user says so. Everything else about governance - roles, audit,
a real policy engine - is Phase 10 and deliberately absent here.

The gate sits between the executor and the tool rather than inside either. In
the executor it would be checked once and forgotten by the next tool; inside
each tool it would be re-implemented per tool, and the one that forgot would be
the one that mattered. Here it is one call on the single path every tool call
takes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

from domain.approvals.gate import assess_call, describe
from domain.approvals.models import ApprovalRequest, ApprovalState
from domain.approvals.protocols import ApprovalService
from domain.employees.definition import EmployeeDefinition
from domain.policies.models import Decision
from domain.secrets.models import redact
from domain.tasks.task import Task
from domain.tools.protocols import RiskAssessor, Tool

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class GateOutcome:
    allowed: bool
    reason: str = ""


ALLOWED = GateOutcome(allowed=True)


class ApprovalGate:
    """Decides, and where needed asks, before a tool runs."""

    def __init__(self, service: ApprovalService | None = None) -> None:
        self._service = service

    async def check(
        self, tool: Tool, input_data: dict[str, Any], task: Task, definition: EmployeeDefinition
    ) -> GateOutcome:
        assessment = tool.assess(input_data) if isinstance(tool, RiskAssessor) else None
        decision = assess_call(tool.spec, assessment)
        if decision.decision is not Decision.REQUIRE_APPROVAL:
            return ALLOWED

        if self._service is None:
            # No configured way to ask means no way to say yes. Refusing is the
            # only answer that cannot do damage.
            return GateOutcome(
                allowed=False,
                reason=(
                    f"{tool.spec.name} needs the user's approval and no approver "
                    "is configured on this machine."
                ),
            )

        request = ApprovalRequest.create(
            task_id=task.id,
            action=describe(tool.spec, input_data),
            payload=redact(input_data),
            risk_level=decision.risk_level,
            workspace_id=task.workspace_id,
            requested_by_employee_id=definition.id,
            reason=decision.reason,
        )
        log.info(
            "approval.requested",
            task_id=str(task.id),
            tool=tool.spec.name,
            risk=decision.risk_level.value,
        )
        state = await self._service.request(request)
        if state is ApprovalState.APPROVED:
            return ALLOWED
        return GateOutcome(
            allowed=False,
            reason=(
                f"The user did not approve this action ({state.value.lower()}): "
                f"{decision.reason}. Do not retry it; find another way or say why you cannot."
            ),
        )
