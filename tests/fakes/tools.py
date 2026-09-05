"""Tool doubles. Real tools arrive in Phase 4; the loop needs some now."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from domain.computer.interfaces import InterfaceLevel
from domain.tools.models import ToolResult, ToolSpec


class FakeTool:
    """Implements `domain.tools.protocols.Tool`."""

    def __init__(
        self,
        name: str,
        *,
        result: ToolResult | None = None,
        handler: Callable[[dict[str, Any]], ToolResult] | None = None,
        raises: Exception | None = None,
        description: str = "A tool that exists for the test.",
        interface_level: InterfaceLevel = InterfaceLevel.API,
    ) -> None:
        self._spec = ToolSpec(
            name=name,
            description=description,
            json_schema={"type": "object", "properties": {}},
            interface_level=interface_level,
        )
        self._result = result or ToolResult.ok(value="ok")
        self._handler = handler
        self._raises = raises
        self.calls: list[dict[str, Any]] = []

    @property
    def spec(self) -> ToolSpec:
        return self._spec

    async def execute(self, input_data: dict[str, Any]) -> ToolResult:
        self.calls.append(input_data)
        if self._raises is not None:
            raise self._raises
        if self._handler is not None:
            return self._handler(input_data)
        return self._result
