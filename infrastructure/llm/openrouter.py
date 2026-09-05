"""OpenRouter - the hosted provider of Phase 2.

OpenRouter speaks the chat-completions shape, so the wire work lives in
`chat_completions.py` and this file only says who we are talking to. Reaching
many models through one endpoint is a convenience, not a commitment: what
callers depend on is `domain.llm.protocols.LLM`.
"""

from __future__ import annotations

from infrastructure.llm.chat_completions import ChatCompletionsProvider

PROVIDER_NAME = "openrouter"
BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterProvider(ChatCompletionsProvider):
    provider_name = PROVIDER_NAME

    def __init__(self, api_key: str, *, base_url: str = BASE_URL, **kwargs: object) -> None:
        super().__init__(api_key, base_url=base_url, **kwargs)  # type: ignore[arg-type]
