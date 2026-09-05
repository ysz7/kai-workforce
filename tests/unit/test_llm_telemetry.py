from __future__ import annotations

from uuid import uuid4

import pytest

from domain.errors import RateLimitError
from domain.llm.models import LLMRequest, Message
from infrastructure.llm.catalog import ModelCatalog
from infrastructure.llm.telemetry import MeteredLLM
from infrastructure.persistence.llm_call_repository import InMemoryLLMCallLog
from tests.fakes.llm import FakeLLM, reply

CATALOG = ModelCatalog.from_dict(
    {
        "models": {
            "priced": {
                "provider": "openrouter",
                "model": "vendor/medium",
                "capabilities": ["TEXT_REASONING"],
                "input_cost_per_1k_usd": 0.003,
                "output_cost_per_1k_usd": 0.015,
            }
        }
    }
)


def ask() -> LLMRequest:
    return LLMRequest(messages=(Message.user("Which city?"),), model="vendor/medium")


def metered(inner, log=None, **kwargs):
    return MeteredLLM(
        inner,
        provider="openrouter",
        catalog=CATALOG,
        call_log=log or InMemoryLLMCallLog(),
        **kwargs,
    )


async def test_a_call_is_priced_from_the_catalog() -> None:
    inner = FakeLLM(
        [reply("Berlin.", model="vendor/medium", prompt_tokens=1000, output_tokens=200)]
    )
    response = await metered(inner).generate(ask())

    # 1000 * 0.003/1000 + 200 * 0.015/1000
    assert response.usage.cost_usd == pytest.approx(0.006)


async def test_every_call_is_written_down() -> None:
    log = InMemoryLLMCallLog()
    inner = FakeLLM([reply("a", model="vendor/medium"), reply("b", model="vendor/medium")])
    client = metered(inner, log)

    await client.generate(ask())
    await client.generate(ask())

    summary = await log.total()
    assert summary.calls == 2
    assert summary.prompt_tokens == 20
    assert summary.cost_usd > 0


async def test_spend_can_be_attributed_to_one_task() -> None:
    log = InMemoryLLMCallLog()
    task_id = uuid4()
    inner = FakeLLM([reply("a", model="vendor/medium"), reply("b", model="vendor/medium")])
    client = metered(inner, log)

    await client.generate(ask())
    await client.for_task(task_id).generate(ask())

    assert (await log.total(task_id)).calls == 1
    assert (await log.total()).calls == 2


async def test_a_failed_call_is_recorded_too() -> None:
    # A run that burned budget and produced nothing is exactly the one you want
    # to find later.
    log = InMemoryLLMCallLog()
    inner = FakeLLM([RateLimitError("slow down")])

    with pytest.raises(RateLimitError):
        await metered(inner, log).generate(ask())

    assert len(log.calls) == 1
    assert log.calls[0].success is False
    assert "RateLimitError" in (log.calls[0].error or "")


async def test_an_unpriced_model_is_reported_at_zero_not_guessed() -> None:
    inner = FakeLLM([reply("hi", model="vendor/unknown")])
    response = await metered(inner).generate(ask())
    assert response.usage.cost_usd == 0.0
