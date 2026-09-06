"""What is happening right now, in the words an interface can show.

A task already leaves two durable traces: its own row, saved after every step,
and the tool-call log. Both are written to be read *afterwards*. Neither answers
the question a person watching a run actually has - what is it doing at this
second - and polling a row that changes once a step is a poor imitation of an
answer.

So the runtime announces its own progress. The contract is deliberately thin:
one value type and one sink. Nothing here knows about HTTP, sockets or a
process; a sink that drops everything is a valid sink, and that is what the CLI
uses. The live view in `app/ui/` subscribes to a sink that keeps a short buffer.

This is not the audit trail and must never be confused with one. Progress is
lossy by design - a subscriber that arrives late has missed what came before,
and the answer to "what happened" is still the task row and the tool-call log.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from domain.workspace.models import DEFAULT_WORKSPACE_ID, WorkspaceId


class ProgressKind(StrEnum):
    """The kinds of thing worth showing a person while a task runs.

    Kept small on purpose: a stream with a category per event type is a log, and
    an interface that has to know forty categories to render a line is coupled
    to the runtime's internals.
    """

    #: The task moved between statuses, or between stages of the runtime.
    STAGE = "STAGE"
    #: A plan was produced. `payload["steps"]` carries it.
    PLAN = "PLAN"
    #: The employee decided to call a tool. Arguments are already redacted.
    TOOL_CALL = "TOOL_CALL"
    #: What the employee made of the result - the same text the model sees.
    OBSERVATION = "OBSERVATION"
    #: An irreversible action is waiting on a person.
    APPROVAL = "APPROVAL"
    #: The run reached a terminal state, successfully or not.
    RESULT = "RESULT"


@dataclass(frozen=True, slots=True)
class ProgressEvent:
    """One thing that just happened, addressed to whoever is watching."""

    task_id: UUID
    kind: ProgressKind
    message: str
    step: int = 0
    payload: dict[str, Any] = field(default_factory=dict)
    workspace_id: WorkspaceId = DEFAULT_WORKSPACE_ID
    at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": str(self.task_id),
            "kind": self.kind.value,
            "message": self.message,
            "step": self.step,
            "payload": self.payload,
            "at": self.at.isoformat(),
        }


class ProgressSink(Protocol):
    """Where progress goes. Never allowed to fail the work it is describing."""

    async def emit(self, event: ProgressEvent) -> None: ...


class NullProgress:
    """The default. A run nobody is watching pays nothing to be watchable."""

    async def emit(self, event: ProgressEvent) -> None:
        return None
