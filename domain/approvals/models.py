from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from domain.policies.models import RiskLevel
from domain.secrets.models import redact
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
    #: Why this action needed asking, in the words shown to the person deciding.
    reason: str = ""

    @classmethod
    def create(cls, task_id: UUID, action: str, **extra: Any) -> ApprovalRequest:
        return cls(id=uuid4(), task_id=task_id, action=action, **extra)

    def redacted(self) -> ApprovalRequest:
        """The form that is safe to show and to store."""
        return replace(self, payload=redact(self.payload))


@dataclass(frozen=True, slots=True)
class Approval:
    """A request plus what was decided about it.

    Kept as one persisted value rather than two tables: the question and the
    answer are read together every time, and a pending request is just one whose
    answer has not arrived.
    """

    request: ApprovalRequest
    state: ApprovalState = ApprovalState.PENDING
    resolved_at: datetime | None = None
    resolved_by: str | None = None
    comment: str = ""

    @property
    def id(self) -> UUID:
        return self.request.id

    @property
    def is_pending(self) -> bool:
        return self.state is ApprovalState.PENDING

    def resolve(
        self, decision: ApprovalState, *, resolved_by: str = "user", comment: str = ""
    ) -> Approval:
        return replace(
            self,
            state=decision,
            resolved_at=datetime.now(UTC),
            resolved_by=resolved_by,
            comment=comment,
        )
