from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

from domain.policies.models import ActorKind
from domain.workspace.models import DEFAULT_WORKSPACE_ID, WorkspaceId


@dataclass(frozen=True, slots=True)
class AuditRecord:
    action: str
    actor_kind: ActorKind
    result: str
    actor_id: str | None = None
    workspace_id: WorkspaceId = DEFAULT_WORKSPACE_ID
    task_id: UUID | None = None
    assignment_id: UUID | None = None
    tool: str | None = None
    model: str | None = None
    cost_usd: float | None = None
    latency_ms: int | None = None
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class AuditLog(Protocol):
    async def record(self, record: AuditRecord) -> None: ...
