"""One local workspace today, a migration away from many.

Every user-owned entity carries a `workspace_id`. There is deliberately no
organization, user or membership table yet: a single developer runs this on
their own machine. The column costs one index now and saves rewriting every
query later.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, NewType

WorkspaceId = NewType("WorkspaceId", str)

DEFAULT_WORKSPACE_ID: Final[WorkspaceId] = WorkspaceId("default")


@dataclass(frozen=True, slots=True)
class WorkspaceScope:
    """The workspace a piece of work belongs to."""

    workspace_id: WorkspaceId = DEFAULT_WORKSPACE_ID

    @classmethod
    def local(cls) -> WorkspaceScope:
        """The single workspace of a local-first installation."""
        return cls(DEFAULT_WORKSPACE_ID)
