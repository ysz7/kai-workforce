from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from domain.capabilities.models import Capability
from domain.policies.models import RiskLevel


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """What a model is told about a tool, plus what the platform needs to gate it."""

    name: str
    description: str
    json_schema: dict[str, Any] = field(default_factory=dict)
    risk_level: RiskLevel = RiskLevel.LOW
    capabilities: frozenset[Capability] = field(default_factory=frozenset)
    reversible: bool = True


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
