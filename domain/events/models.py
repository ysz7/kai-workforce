from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from domain.workspace.models import DEFAULT_WORKSPACE_ID, WorkspaceId


@dataclass(frozen=True, slots=True)
class DomainEvent:
    """Something that happened. Named in the past tense: `task.completed`."""

    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    id: UUID = field(default_factory=uuid4)
    workspace_id: WorkspaceId = DEFAULT_WORKSPACE_ID
    correlation_id: str | None = None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class EventBus(Protocol):
    async def publish(self, event: DomainEvent) -> None: ...

    def subscribe(self, event_type: str, handler: Any) -> None: ...
