from __future__ import annotations

from typing import Protocol
from uuid import UUID

from domain.approvals.models import ApprovalRequest, ApprovalState


class ApprovalService(Protocol):
    async def request(self, action: ApprovalRequest) -> ApprovalState: ...

    async def resolve(self, approval_id: UUID, decision: ApprovalState) -> None: ...
