"""Memory values. The backend lands in Phase 9; the vocabulary is fixed now."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from domain.workspace.models import DEFAULT_WORKSPACE_ID, WorkspaceId


class MemoryScope(StrEnum):
    """Scope is an access boundary, not a hint.

    An employee never reads another employee's EMPLOYEE_PRIVATE memory.
    """

    WORKSPACE = "WORKSPACE"
    PLAN = "PLAN"
    EMPLOYEE_PRIVATE = "EMPLOYEE_PRIVATE"


class MemoryKind(StrEnum):
    WORKING = "WORKING"
    EPISODIC = "EPISODIC"
    SEMANTIC = "SEMANTIC"
    PROCEDURAL = "PROCEDURAL"


@dataclass(frozen=True, slots=True)
class MemoryItem:
    id: UUID
    workspace_id: WorkspaceId
    scope: MemoryScope
    kind: MemoryKind
    content: str
    employee_id: UUID | None = None
    plan_id: UUID | None = None
    task_id: UUID | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    importance: float = 0.5
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None

    @classmethod
    def create(
        cls,
        content: str,
        *,
        scope: MemoryScope,
        kind: MemoryKind,
        workspace_id: WorkspaceId = DEFAULT_WORKSPACE_ID,
        **extra: Any,
    ) -> MemoryItem:
        return cls(
            id=uuid4(),
            workspace_id=workspace_id,
            scope=scope,
            kind=kind,
            content=content,
            **extra,
        )


@dataclass(frozen=True, slots=True)
class MemoryQuery:
    """Every recall is scoped. There is no unscoped read."""

    text: str = ""
    workspace_id: WorkspaceId = DEFAULT_WORKSPACE_ID
    scopes: frozenset[MemoryScope] = field(
        default_factory=lambda: frozenset({MemoryScope.WORKSPACE})
    )
    kinds: frozenset[MemoryKind] = field(default_factory=frozenset)
    employee_id: UUID | None = None
    plan_id: UUID | None = None
    task_id: UUID | None = None
    limit: int = 20
