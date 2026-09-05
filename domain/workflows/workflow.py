from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID

from domain.workspace.models import DEFAULT_WORKSPACE_ID, WorkspaceId


@dataclass(frozen=True, slots=True)
class WorkflowContext:
    run_id: UUID
    inputs: dict[str, Any] = field(default_factory=dict)
    workspace_id: WorkspaceId = DEFAULT_WORKSPACE_ID
    correlation_id: str | None = None


@dataclass(frozen=True, slots=True)
class WorkflowResult:
    success: bool
    summary: str = ""
    output: dict[str, Any] = field(default_factory=dict)


class Workflow(Protocol):
    @property
    def name(self) -> str: ...

    async def execute(self, context: WorkflowContext) -> WorkflowResult: ...
