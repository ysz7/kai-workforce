"""Anthropic adapter - not implemented yet.

Phase 2 ships one working provider on purpose. The contract is what had to be
fixed early, and it is; this file records what filling it in will involve.

Anthropic uses a different message shape - the system prompt is a top-level
field, and tool results are content blocks rather than a role.
"""

from __future__ import annotations

from domain.errors import ConfigurationError
from domain.llm.models import LLMRequest, LLMResponse

PROVIDER_NAME = "anthropic"
BASE_URL = "https://api.anthropic.com/v1"


class AnthropicProvider:
    """Will implement `domain.llm.protocols.LLM`."""

    def __init__(self, api_key: str, *, base_url: str = BASE_URL) -> None:
        self._api_key = api_key
        self._base_url = base_url

    async def generate(self, request: LLMRequest) -> LLMResponse:
        raise ConfigurationError(
            f"The {PROVIDER_NAME} adapter is not implemented yet. "
            "Phase 2 ships one provider; see infrastructure/llm/README.md."
        )
