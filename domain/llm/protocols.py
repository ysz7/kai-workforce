from __future__ import annotations

from typing import Protocol

from domain.capabilities.models import CapabilityRequirement
from domain.llm.models import LLMRequest, LLMResponse, ModelChoice, RoutingHints, TaskKind


class LLM(Protocol):
    async def generate(self, request: LLMRequest) -> LLMResponse: ...


class ModelRouter(Protocol):
    """Employees and KAI both route through this. The manager is not a special case."""

    def select(
        self,
        task_kind: TaskKind,
        required: CapabilityRequirement,
        hints: RoutingHints,
    ) -> ModelChoice: ...


class LLMFactory(Protocol):
    """Turns a routing decision into a client.

    Callers pick a model by capability and get back something they can talk to,
    without ever naming a provider.
    """

    def for_choice(self, choice: ModelChoice) -> LLM: ...
