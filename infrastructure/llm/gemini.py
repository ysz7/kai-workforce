"""Gemini adapter - not implemented yet.

Phase 2 ships one working provider on purpose. The contract is what had to be
fixed early, and it is; this file records what filling it in will involve.

Gemini uses a different vocabulary again - contents and parts instead of
messages, functionDeclarations instead of tools.
"""

from __future__ import annotations

from domain.errors import ConfigurationError
from domain.llm.models import LLMRequest, LLMResponse

PROVIDER_NAME = "gemini"
BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class GeminiProvider:
    """Will implement `domain.llm.protocols.LLM`."""

    def __init__(self, api_key: str, *, base_url: str = BASE_URL) -> None:
        self._api_key = api_key
        self._base_url = base_url

    async def generate(self, request: LLMRequest) -> LLMResponse:
        raise ConfigurationError(
            f"The {PROVIDER_NAME} adapter is not implemented yet. "
            "Phase 2 ships one provider; see infrastructure/llm/README.md."
        )
