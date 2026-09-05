"""Turns a routing decision into a client, with metering attached.

This is the one place that maps a provider name to a class. A caller asks the
router for a model and this for a client, and never learns which vendor answered.
"""

from __future__ import annotations

from domain.errors import ConfigurationError
from domain.llm.models import ModelChoice
from domain.llm.protocols import LLM
from domain.llm.telemetry import LLMCallLog
from infrastructure.llm.anthropic import AnthropicProvider
from infrastructure.llm.catalog import ModelCatalog
from infrastructure.llm.gemini import GeminiProvider
from infrastructure.llm.local import BASE_URL as LOCAL_BASE_URL
from infrastructure.llm.local import LocalProvider
from infrastructure.llm.openai import OpenAIProvider
from infrastructure.llm.openrouter import OpenRouterProvider
from infrastructure.llm.retry import RetryPolicy
from infrastructure.llm.telemetry import MeteredLLM


class ProviderFactory:
    """Implements `domain.llm.protocols.LLMFactory`."""

    def __init__(
        self,
        *,
        catalog: ModelCatalog,
        api_key: str | None,
        base_url: str,
        local_base_url: str = LOCAL_BASE_URL,
        call_log: LLMCallLog | None = None,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self._catalog = catalog
        self._api_key = api_key
        self._base_url = base_url
        self._local_base_url = local_base_url
        self._call_log = call_log
        self._retry_policy = retry_policy
        self._clients: dict[tuple[str, str], LLM] = {}

    def for_choice(self, choice: ModelChoice) -> LLM:
        key = (choice.provider, choice.model)
        if key not in self._clients:
            self._clients[key] = MeteredLLM(
                self._build(choice),
                provider=choice.provider,
                catalog=self._catalog,
                call_log=self._call_log,
            )
        return self._clients[key]

    def _build(self, choice: ModelChoice) -> LLM:
        if choice.provider == "openrouter":
            return OpenRouterProvider(
                self._require_key(choice.provider),
                base_url=self._base_url,
                default_model=choice.model,
                retry_policy=self._retry_policy,
            )
        if choice.provider == "openai":
            return OpenAIProvider(self._require_key(choice.provider))
        if choice.provider == "anthropic":
            return AnthropicProvider(self._require_key(choice.provider))
        if choice.provider == "gemini":
            return GeminiProvider(self._require_key(choice.provider))
        if choice.provider == "local":
            return LocalProvider(
                base_url=self._local_base_url,
                default_model=choice.model,
                retry_policy=self._retry_policy,
            )
        raise ConfigurationError(
            f"Unknown provider '{choice.provider}'. Providers are registered in "
            "infrastructure/llm/factory.py and their models in models.toml."
        )

    def _require_key(self, provider: str) -> str:
        if not self._api_key:
            raise ConfigurationError(
                f"No API key configured for '{provider}'. Set KAI_LLM_API_KEY in .env."
            )
        return self._api_key

    async def aclose(self) -> None:
        for client in self._clients.values():
            inner = getattr(client, "_inner", client)
            closer = getattr(inner, "aclose", None)
            if closer is not None:
                await closer()
        self._clients.clear()
