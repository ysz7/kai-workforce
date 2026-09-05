"""OpenAI adapter - not implemented yet.

Phase 2 ships one working provider on purpose. The contract is what had to be
fixed early, and it is; this file records what filling it in will involve.

OpenAI uses the same chat-completions shape as the implemented adapter, so
this is mostly a base URL and an auth header.
"""

from __future__ import annotations

from domain.errors import ConfigurationError
from domain.llm.models import LLMRequest, LLMResponse

PROVIDER_NAME = "openai"
BASE_URL = "https://api.openai.com/v1"


class OpenAIProvider:
    """Will implement `domain.llm.protocols.LLM`."""

    def __init__(self, api_key: str, *, base_url: str = BASE_URL) -> None:
        self._api_key = api_key
        self._base_url = base_url

    async def generate(self, request: LLMRequest) -> LLMResponse:
        raise ConfigurationError(
            f"The {PROVIDER_NAME} adapter is not implemented yet. "
            "Phase 2 ships one provider; see infrastructure/llm/README.md."
        )
