from __future__ import annotations

from typing import Any, Protocol

from domain.policies.models import Actor
from domain.tools.models import ToolResult, ToolSpec


class Tool(Protocol):
    @property
    def spec(self) -> ToolSpec: ...

    async def execute(self, input_data: dict[str, Any]) -> ToolResult: ...


class ToolRegistry(Protocol):
    """Permissions are enforced here, not in the caller.

    An actor only ever sees the specs it is allowed to use, so a model cannot ask
    for a tool it has no right to.
    """

    def register(self, tool: Tool) -> None: ...

    def get(self, name: str, actor: Actor) -> Tool: ...

    def list_specs(self, actor: Actor) -> list[ToolSpec]: ...
