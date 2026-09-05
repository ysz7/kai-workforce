"""What a tool call cost and whether it worked.

Model calls have been accounted for since Phase 2 for a reason that applies to
tools just as much: a loop that is failing does not announce itself, it just
keeps calling. Recorded per call, arguments redacted, so a run can be read back
afterwards without leaking a credential into the store.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

from domain.secrets.models import redact


@dataclass(frozen=True, slots=True)
class ToolCallRecord:
    tool: str
    success: bool
    latency_ms: int = 0
    task_id: UUID | None = None
    input_data: dict[str, Any] = field(default_factory=dict)
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def redacted(self) -> ToolCallRecord:
        """The form that is safe to store: no argument named like a credential."""
        return ToolCallRecord(
            tool=self.tool,
            success=self.success,
            latency_ms=self.latency_ms,
            task_id=self.task_id,
            input_data=redact(self.input_data),
            output=redact(self.output),
            error=self.error,
            created_at=self.created_at,
        )


class ToolCallLog(Protocol):
    """Where every tool call is accounted for."""

    async def record(self, call: ToolCallRecord) -> None: ...

    async def list_for_task(self, task_id: UUID) -> list[ToolCallRecord]: ...
