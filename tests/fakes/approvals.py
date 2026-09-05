"""Approval doubles: a decision the test controls, and a record of what was asked."""

from __future__ import annotations

from uuid import UUID

from domain.approvals.models import ApprovalRequest, ApprovalState


class ScriptedApprovalService:
    """Implements `domain.approvals.protocols.ApprovalService`."""

    def __init__(self, *decisions: ApprovalState, default: ApprovalState | None = None) -> None:
        self._decisions = list(decisions)
        self._default = default or ApprovalState.REJECTED
        self.requests: list[ApprovalRequest] = []

    @classmethod
    def approving(cls) -> ScriptedApprovalService:
        return cls(default=ApprovalState.APPROVED)

    @classmethod
    def rejecting(cls) -> ScriptedApprovalService:
        return cls(default=ApprovalState.REJECTED)

    async def request(self, action: ApprovalRequest) -> ApprovalState:
        self.requests.append(action)
        return self._decisions.pop(0) if self._decisions else self._default

    async def resolve(
        self,
        approval_id: UUID,
        decision: ApprovalState,
        *,
        resolved_by: str = "user",
        comment: str = "",
    ) -> None:  # pragma: no cover - a scripted service answers immediately
        raise NotImplementedError
