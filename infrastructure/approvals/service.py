"""Asking the person at the keyboard, and remembering what they said.

Three modes, because the honest answer differs by situation and guessing is
worse than configuring:

* **prompt** - a human is at a terminal, so ask them.
* **deny** - nobody is there (a scheduled run, a test, a piped process). The
  action is refused and recorded as refused. Silence is not consent.
* **allow** - the user has explicitly said they do not want to be asked on this
  machine. Still recorded, so `kai approvals` shows what was done under it.

Who gets asked is a separate question from whether to ask, and that is why the
confirmer is injected. On a terminal it reads stdin; under the local interface
it is a coroutine that parks until someone clicks in the browser. The rule -
anything but an explicit yes is a no - is the same either way, and lives in the
confirmer rather than being re-decided here.

Every request is written to the database *before* it is answered. A process
killed while waiting for a decision leaves a PENDING row, which is what makes
the question survivable rather than lost.
"""

from __future__ import annotations

import inspect
import sys
from collections.abc import Awaitable, Callable
from enum import StrEnum
from uuid import UUID

from domain.approvals.models import Approval, ApprovalRequest, ApprovalState
from domain.approvals.protocols import ApprovalRepository
from domain.errors import NotFoundError
from infrastructure.observability.logging import get_logger

log = get_logger(__name__)

#: Sync or async: a terminal answers immediately, a browser does not.
Confirmer = Callable[[ApprovalRequest], "bool | Awaitable[bool]"]


class ApprovalMode(StrEnum):
    PROMPT = "prompt"
    DENY = "deny"
    ALLOW = "allow"


def console_confirmer(request: ApprovalRequest) -> bool:
    """Ask on the terminal. Anything but an explicit yes is a no."""
    safe = request.redacted()
    print(f"\nApproval needed: {safe.action}", file=sys.stderr)
    if safe.reason:
        print(f"  why:  {safe.reason}", file=sys.stderr)
    print(f"  risk: {safe.risk_level.value}", file=sys.stderr)
    try:
        answer = input("Allow this action? [y/N] ")
    except (EOFError, KeyboardInterrupt):
        print(file=sys.stderr)
        return False
    return answer.strip().lower() in {"y", "yes"}


class LocalApprovalService:
    """Implements `domain.approvals.protocols.ApprovalService`."""

    def __init__(
        self,
        repository: ApprovalRepository,
        *,
        mode: ApprovalMode | str = ApprovalMode.PROMPT,
        confirmer: Confirmer | None = None,
        is_interactive: Callable[[], bool] = lambda: sys.stdin is not None and sys.stdin.isatty(),
    ) -> None:
        self._repository = repository
        self._mode = ApprovalMode(mode)
        self._confirmer = confirmer or console_confirmer
        self._is_interactive = is_interactive

    async def request(self, action: ApprovalRequest) -> ApprovalState:
        approval = Approval(request=action.redacted())
        await self._repository.save(approval)

        decision, resolved_by = await self._decide(action)
        await self._repository.save(
            approval.resolve(decision, resolved_by=resolved_by, comment=action.reason)
        )
        log.info(
            "approval.resolved",
            approval_id=str(action.id),
            action=action.action,
            risk=action.risk_level.value,
            state=decision.value,
            resolved_by=resolved_by,
        )
        return decision

    async def _decide(self, action: ApprovalRequest) -> tuple[ApprovalState, str]:
        if self._mode is ApprovalMode.ALLOW:
            return ApprovalState.APPROVED, "configuration"
        if self._mode is ApprovalMode.DENY or not self._is_interactive():
            return ApprovalState.REJECTED, "no-approver"
        answer = self._confirmer(action.redacted())
        approved = await answer if inspect.isawaitable(answer) else answer
        return (ApprovalState.APPROVED if approved else ApprovalState.REJECTED), "user"

    async def resolve(
        self,
        approval_id: UUID,
        decision: ApprovalState,
        *,
        resolved_by: str = "user",
        comment: str = "",
    ) -> None:
        approval = await self._repository.get(approval_id)
        if approval is None:
            raise NotFoundError(f"Unknown approval: {approval_id}")
        await self._repository.save(
            approval.resolve(decision, resolved_by=resolved_by, comment=comment)
        )
