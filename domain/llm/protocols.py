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
