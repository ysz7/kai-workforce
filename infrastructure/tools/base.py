"""What every tool gets for free, so a new tool is one small file.

Validation, timing and failure handling are identical for every tool, and a
tool that re-implements them re-implements them slightly differently. Here they
happen once: a subclass declares its `ToolSpec` and writes `run`, and a bad
argument comes back to the model as a message it can act on rather than as an
exception that ends the task.
"""

from __future__ import annotations

import time
from typing import Any

from domain.errors import DomainError
from domain.tools.models import ToolResult, ToolSpec
from infrastructure.observability.logging import get_logger

log = get_logger(__name__)


class BaseTool:
    """Implements `domain.tools.protocols.Tool`."""

    def __init__(self, spec: ToolSpec) -> None:
        self._spec = spec

    @property
    def spec(self) -> ToolSpec:
        return self._spec

    async def execute(self, input_data: dict[str, Any]) -> ToolResult:
        started = time.perf_counter()
        ignored = self._spec.parameters.unknown(input_data)
        try:
            arguments = self._spec.parameters.validate(input_data)
        except DomainError as error:
            # A wrong argument is information for the model, not a crash: it can
            # read the message and call the tool correctly on the next step - but
            # only if the message says what the right call looks like. Listing
            # what was wrong without showing the shape leaves a weaker model
            # guessing, and a guessing model repeats itself until the step limit.
            return ToolResult.failure(
                f"{error}. Call {self._spec.name} like this: "
                f"{self._spec.parameters.example()}"
            )

        try:
            result = await self.run(**arguments)
        except DomainError as error:
            result = ToolResult.failure(f"{type(error).__name__}: {error}")
        except Exception as error:  # a tool must not take the task down with it
            log.warning("tool.raised", tool=self._spec.name, error=str(error))
            result = ToolResult.failure(f"{type(error).__name__}: {error}")

        latency_ms = int((time.perf_counter() - started) * 1000)
        output = result.output
        if ignored and result.success:
            # Dropped, not swallowed: the model sees which of its arguments did
            # nothing, and can stop sending them.
            log.info("tool.ignored_arguments", tool=self._spec.name, arguments=ignored)
            output = {**output, "ignored_arguments": ignored}
        return ToolResult(
            success=result.success,
            output=output,
            error=result.error,
            latency_ms=result.latency_ms or latency_ms,
        )

    async def run(self, **arguments: Any) -> ToolResult:
        raise NotImplementedError
