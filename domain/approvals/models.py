from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from domain.policies.models import RiskLevel
from domain.workspace.models import DEFAULT_WORKSPACE_ID, WorkspaceId


class ApprovalState(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    """A human decision an irreversible action is waiting on.

    Only a human resolves these. KAI can ask; it can never approve its own work.
    """

    id: UUID
    task_id: UUID
    action: str
    payload: dict[str, Any] = field(default_factory=dict)
    risk_level: RiskLevel = RiskLevel.HIGH
    workspace_id: WorkspaceId = DEFAULT_WORKSPACE_ID
    requested_by_employee_id: UUID | None = None
    requested_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(cls, task_id: UUID, action: str, **extra: Any) -> ApprovalRequest:
        return cls(id=uuid4(), task_id=task_id, action=action, **extra)
