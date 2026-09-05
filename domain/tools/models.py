from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from domain.capabilities.models import Capability
from domain.policies.models import RiskLevel
from domain.tools.schema import Param, ParameterSet


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """What a model is told about a tool, plus what the platform needs to gate it."""

    name: str
    description: str
    json_schema: dict[str, Any] = field(default_factory=dict)
    risk_level: RiskLevel = RiskLevel.LOW
    capabilities: frozenset[Capability] = field(default_factory=frozenset)
    reversible: bool = True
    #: The declared parameters, kept alongside the rendered schema so the same
    #: declaration both describes the tool and validates the call.
    parameters: ParameterSet = field(default_factory=ParameterSet)

    @classmethod
    def of(
        cls,
        name: str,
        description: str,
        *parameters: Param,
        risk_level: RiskLevel = RiskLevel.LOW,
        capabilities: frozenset[Capability] = frozenset(),
        reversible: bool = True,
    ) -> ToolSpec:
        """Declare a tool once; the JSON Schema is derived, never hand-written."""
        parameter_set = ParameterSet(parameters)
        return cls(
            name=name,
            description=description,
            json_schema=parameter_set.to_json_schema(),
            risk_level=risk_level,
            capabilities=capabilities,
            reversible=reversible,
            parameters=parameter_set,
        )


@dataclass(frozen=True, slots=True)
class ToolCall:
    name: str
    input_data: dict[str, Any] = field(default_factory=dict)
    call_id: str | None = None


@dataclass(frozen=True, slots=True)
class ToolResult:
    success: bool
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    latency_ms: int = 0

    @classmethod
    def ok(cls, **output: Any) -> ToolResult:
        return cls(success=True, output=output)

    @classmethod
    def failure(cls, error: str) -> ToolResult:
        return cls(success=False, error=error)
