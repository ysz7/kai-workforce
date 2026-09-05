"""The tool registry: permissions live here, not in the caller.

Phase 3 needs this to run the executor at all; the tools that fill it arrive in
Phase 4. Filtering by actor is the point of the class, not an extra: a model can
only ask for a tool it was shown, so showing it only what the employee is
allowed to use removes a whole class of refusal-and-retry turns.
"""

from __future__ import annotations

from domain.errors import PermissionDeniedError, ToolNotFoundError
from domain.policies.models import Actor
from domain.tools.models import ToolSpec
from domain.tools.protocols import Tool


class InMemoryToolRegistry:
    """Implements `domain.tools.protocols.ToolRegistry`."""

    def __init__(self, tools: list[Tool] | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools or []:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        self._tools[tool.spec.name] = tool

    def get(self, name: str, actor: Actor) -> Tool:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolNotFoundError(name)
        if not self._is_allowed(name, actor):
            raise PermissionDeniedError(
                f"{actor.actor_kind} '{actor.actor_id}' may not use '{name}'"
            )
        return tool

    def list_specs(self, actor: Actor) -> list[ToolSpec]:
        return [
            tool.spec
            for name, tool in sorted(self._tools.items())
            if self._is_allowed(name, actor)
        ]

    def _is_allowed(self, name: str, actor: Actor) -> bool:
        """Least privilege: an actor gets what it lists, and nothing by default.

        A wildcard is supported because a human at a terminal is a different case
        from an autonomous employee - but it has to be asked for explicitly.
        """
        allowed = actor.allowed_tools
        return "*" in allowed or name in allowed
