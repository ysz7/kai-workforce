"""Provider-neutral request and response values.

No vendor name appears in this module, or anywhere else under `domain/`.
Adapters in `infrastructure/llm/` translate to and from these.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from domain.capabilities.models import Capability, CapabilityRequirement
from domain.tools.models import ToolSpec


class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass(frozen=True, slots=True)
class ToolCallRequest:
    """A tool invocation the model asked for."""

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Message:
    role: Role
    content: str
    name: str | None = None
    tool_call_id: str | None = None
    #: Set on an assistant message that asked for tools, so a follow-up request
    #: can replay the exchange the provider expects.
    tool_calls: tuple[ToolCallRequest, ...] = ()

    @classmethod
    def system(cls, content: str) -> Message:
        return cls(Role.SYSTEM, content)

    @classmethod
    def user(cls, content: str) -> Message:
        return cls(Role.USER, content)

    @classmethod
    def assistant(cls, content: str, tool_calls: tuple[ToolCallRequest, ...] = ()) -> Message:
        return cls(Role.ASSISTANT, content, tool_calls=tool_calls)

    @classmethod
    def tool(cls, content: str, tool_call_id: str) -> Message:
        return cls(Role.TOOL, content, tool_call_id=tool_call_id)


@dataclass(frozen=True, slots=True)
class Usage:
    prompt_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0


class FinishReason(StrEnum):
    STOP = "stop"
    LENGTH = "length"
    TOOL_CALLS = "tool_calls"
    CONTENT_FILTER = "content_filter"
    ERROR = "error"


class TaskKind(StrEnum):
    """What a call is for. The router maps this onto a model choice."""

    PLANNING = "PLANNING"
    EXECUTION = "EXECUTION"
    VERIFICATION = "VERIFICATION"
    SYNTHESIS = "SYNTHESIS"
    EXTRACTION = "EXTRACTION"
    CONVERSATION = "CONVERSATION"


@dataclass(frozen=True, slots=True)
class ModelProfile:
    """What an employee needs from a model, never which vendor to use."""

    capabilities: frozenset[Capability] = field(
        default_factory=lambda: frozenset({Capability.TEXT_REASONING})
    )
    min_context_tokens: int | None = None
    max_cost_per_1k_usd: float | None = None
    temperature: float = 0.2

    def as_requirement(self) -> CapabilityRequirement:
        return CapabilityRequirement(
            required=self.capabilities, min_context_tokens=self.min_context_tokens
        )


@dataclass(frozen=True, slots=True)
class RoutingHints:
    quality: float = 0.5
    latency_sensitivity: float = 0.5
    cost_sensitivity: float = 0.5
    context_tokens: int | None = None
    needs_tools: bool = False


@dataclass(frozen=True, slots=True)
class ModelChoice:
    provider: str
    model: str
    reason: str = ""


@dataclass(frozen=True, slots=True)
class LLMRequest:
    """What the platform asks of a model.

    `tools` carries domain tool specs, not a provider's JSON shape: turning them
    into whatever the wire format wants is the adapter's job.
    """

    messages: tuple[Message, ...]
    model: str | None = None
    tools: tuple[ToolSpec, ...] = ()
    temperature: float = 0.2
    max_tokens: int | None = None
    response_format: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class LLMResponse:
    content: str
    model: str
    tool_calls: tuple[ToolCallRequest, ...] = ()
    usage: Usage = field(default_factory=Usage)
    finish_reason: FinishReason = FinishReason.STOP
