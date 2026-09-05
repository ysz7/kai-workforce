from __future__ import annotations

from typing import Protocol
from uuid import UUID

from domain.approvals.models import Approval, ApprovalRequest, ApprovalState
from domain.workspace.models import DEFAULT_WORKSPACE_ID, WorkspaceId


class ApprovalService(Protocol):
    """Asks a human, and reports what they said.

    `request` blocks the action until it has an answer. A service that cannot
    reach a human answers REJECTED rather than APPROVED: the default for an
    irreversible action nobody confirmed is not to do it.
    """

    async def request(self, action: ApprovalRequest) -> ApprovalState: ...

    async def resolve(
        self,
        approval_id: UUID,
        decision: ApprovalState,
        *,
        resolved_by: str = "user",
        comment: str = "",
    ) -> None: ...


class ApprovalRepository(Protocol):
    async def save(self, approval: Approval) -> None: ...

    async def get(self, approval_id: UUID) -> Approval | None: ...

    async def list_pending(
        self, workspace_id: WorkspaceId = DEFAULT_WORKSPACE_ID
    ) -> list[Approval]: ...
