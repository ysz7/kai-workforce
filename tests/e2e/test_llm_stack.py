"""The whole Phase 2 path, end to end, with no network.

Router picks a model, the factory builds a client for it, the adapter talks to a
mock transport, and the metering layer prices the call and writes it to SQLite.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from domain.capabilities.models import Capability, CapabilityRequirement
from domain.errors import ConfigurationError
from domain.llm.models import LLMRequest, Message, RoutingHints, TaskKind
from infrastructure.llm.catalog import ModelCatalog
from infrastructure.llm.factory import ProviderFactory
from infrastructure.llm.openrouter import OpenRouterProvider
from infrastructure.llm.router import CapabilityAwareModelRouter
from infrastructure.persistence.llm_call_repository import SqliteLLMCallLog
from infrastructure.persistence.models import Base
from infrastructure.persistence.session import create_engine, create_session_factory

CATALOG = {
    "models": {
        "balanced": {
            "provider": "openrouter",
            "model": "vendor/medium",
            "capabilities": ["TEXT_REASONING", "TOOL_CALLING"],
            "context_tokens": 200000,
            "input_cost_per_1k_usd": 0.003,
            "output_cost_per_1k_usd": 0.015,
            "quality": 0.8,
        },
        "seeing": {
            "provider": "openrouter",
            "model": "vendor/vision",
            "capabilities": ["TEXT_REASONING", "VISION"],
            "context_tokens": 100000,
            "input_cost_per_1k_usd": 0.01,
            "output_cost_per_1k_usd": 0.03,
            "quality": 0.9,
        },
    },
    "defaults": {"conversation": "balanced"},
}


def _completion(model: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": model,
            "choices": [{"message": {"content": "Berlin."}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1000, "completion_tokens": 200},
        },
    )


async def test_a_question_is_routed_answered_priced_and_recorded(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'kai.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    call_log = SqliteLLMCallLog(create_session_factory(engine))

    catalog = ModelCatalog.from_dict(CATALOG)
    router = CapabilityAwareModelRouter(catalog)
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen["model"] = json.loads(request.content)["model"]
        return _completion(seen["model"])

    transport = httpx.MockTransport(handler)

    class TestableFactory(ProviderFactory):
        def _build(self, choice):
            return OpenRouterProvider(
                "test-key",
                default_model=choice.model,
                client=httpx.AsyncClient(transport=transport),
            )

    factory = TestableFactory(
        catalog=catalog, api_key="test-key", base_url="https://example.invalid/v1",
        call_log=call_log,
    )

    choice = router.select(TaskKind.CONVERSATION, CapabilityRequirement(), RoutingHints())
    client = factory.for_choice(choice)
    response = await client.generate(
        LLMRequest(messages=(Message.user("Which city?"),), model=choice.model)
    )

    assert response.content == "Berlin."
    assert seen["model"] == "vendor/medium"
    # 1000 * 0.003/1000 + 200 * 0.015/1000
    assert response.usage.cost_usd == pytest.approx(0.006)

    summary = await call_log.total()
    assert summary.calls == 1
    assert summary.cost_usd == pytest.approx(0.006)

    await engine.dispose()


async def test_a_capability_requirement_reaches_a_different_model(tmp_path: Path) -> None:
    router = CapabilityAwareModelRouter(ModelCatalog.from_dict(CATALOG))

    plain = router.select(TaskKind.CONVERSATION, CapabilityRequirement(), RoutingHints())
    seeing = router.select(
        TaskKind.CONVERSATION,
        CapabilityRequirement(required=frozenset({Capability.VISION})),
        RoutingHints(),
    )

    assert plain.model == "vendor/medium"
    assert seeing.model == "vendor/vision"


async def test_a_missing_key_fails_before_any_request_is_made() -> None:
    catalog = ModelCatalog.from_dict(CATALOG)
    factory = ProviderFactory(
        catalog=catalog, api_key=None, base_url="https://example.invalid/v1"
    )

    with pytest.raises(ConfigurationError, match="KAI_LLM_API_KEY"):
        factory.for_choice(catalog.get("balanced").choice)
