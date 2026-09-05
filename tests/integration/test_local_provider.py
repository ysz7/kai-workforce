"""The adapter against a real model, when one is running locally.

Everything else in the suite runs on `FakeLLM` and a mock transport, which pins
down shapes but cannot tell you whether a real model accepts them. These tests
close that gap without a key and without spending anything - and skip themselves
when there is no local server, so CI stays green and offline.

Start one with:

    ollama serve
    ollama pull gpt-oss:20b
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest

from domain.capabilities.models import Capability
from domain.llm.models import FinishReason, LLMRequest, Message
from domain.tools.models import ToolSpec
from infrastructure.llm.catalog import ModelCatalog
from infrastructure.llm.local import BASE_URL, LocalProvider
from infrastructure.llm.telemetry import MeteredLLM
from infrastructure.persistence.llm_call_repository import InMemoryLLMCallLog

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCAL_CATALOG = ModelCatalog.load(REPO_ROOT / "infrastructure/llm/models.local.toml")
MODEL = os.environ.get("KAI_TEST_LOCAL_MODEL", "gpt-oss:20b")


def _served_models() -> set[str]:
    try:
        response = httpx.get(f"{BASE_URL}/models", timeout=2.0)
        response.raise_for_status()
    except httpx.HTTPError:
        return set()
    return {entry["id"] for entry in response.json().get("data", [])}


pytestmark = pytest.mark.skipif(
    MODEL not in _served_models(),
    reason=f"No local model server at {BASE_URL} serving {MODEL}",
)


@pytest.fixture
async def provider():
    client = LocalProvider(default_model=MODEL)
    yield client
    await client.aclose()


async def test_a_real_model_answers_and_reports_its_usage(provider) -> None:
    response = await provider.generate(
        LLMRequest(
            messages=(
                Message.system("Answer in one word."),
                Message.user("Which city is the capital of France?"),
            ),
            temperature=0.0,
        )
    )

    assert "paris" in response.content.lower()
    assert response.model == MODEL
    assert response.usage.prompt_tokens > 0
    assert response.usage.output_tokens > 0
    assert response.usage.latency_ms > 0


async def test_a_real_model_calls_a_tool_and_uses_its_result(provider) -> None:
    """The whole tool round trip, which mock tests can only assert the shape of."""
    tool = ToolSpec(
        name="get_weather",
        description="Get the current weather for a city.",
        json_schema={
            "type": "object",
            "properties": {"city": {"type": "string", "description": "City name"}},
            "required": ["city"],
        },
        capabilities=frozenset({Capability.WEB_BROWSING}),
    )
    question = Message.user("What is the weather in Berlin right now?")

    asked = await provider.generate(
        LLMRequest(messages=(question,), tools=(tool,), temperature=0.0)
    )

    assert asked.finish_reason is FinishReason.TOOL_CALLS
    assert asked.tool_calls, "the model was expected to reach for the tool"
    call = asked.tool_calls[0]
    assert call.name == "get_weather"
    assert call.arguments.get("city", "").lower() == "berlin"

    # Replaying the exchange is the part most likely to be rejected on the wire.
    answered = await provider.generate(
        LLMRequest(
            messages=(
                question,
                Message.assistant(asked.content, tool_calls=asked.tool_calls),
                Message.tool('{"temperature_c": 14, "conditions": "rain"}', call.id),
            ),
            tools=(tool,),
            temperature=0.0,
        )
    )

    assert "14" in answered.content
    assert answered.finish_reason is FinishReason.STOP


async def test_a_local_call_is_metered_at_zero_and_still_recorded(provider) -> None:
    # Free is not the same as unaccounted for: token counts still matter for
    # context budgeting, and the call still belongs in the log.
    call_log = InMemoryLLMCallLog()
    metered = MeteredLLM(
        provider, provider="local", catalog=LOCAL_CATALOG, call_log=call_log
    )

    response = await metered.generate(
        LLMRequest(messages=(Message.user("Say 'ok' and nothing else."),), temperature=0.0)
    )

    assert response.usage.cost_usd == 0.0
    summary = await call_log.total()
    assert summary.calls == 1
    assert summary.prompt_tokens > 0
