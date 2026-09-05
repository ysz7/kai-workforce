from __future__ import annotations

import httpx
import pytest

from domain.errors import InvalidRequestError, ProviderUnavailableError, RateLimitError
from infrastructure.llm.openrouter import OpenRouterProvider
from infrastructure.llm.retry import RetryPolicy, with_retry
from tests.fakes.llm import FakeLLM, reply, transient


class Clock:
    """Records what we would have slept for, and sleeps for none of it."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    async def sleep(self, seconds: float) -> None:
        self.delays.append(seconds)


async def test_a_transient_failure_is_retried_until_it_succeeds() -> None:
    attempts = {"n": 0}
    clock = Clock()

    async def flaky() -> str:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RateLimitError("slow down")
        return "ok"

    result = await with_retry(flaky, RetryPolicy(attempts=3), sleep=clock.sleep)

    assert result == "ok"
    assert attempts["n"] == 3
    assert len(clock.delays) == 2


async def test_a_rejected_request_is_not_retried() -> None:
    # Sending the same bad payload again spends the budget and gets the same
    # answer.
    attempts = {"n": 0}
    clock = Clock()

    async def rejected() -> str:
        attempts["n"] += 1
        raise InvalidRequestError("malformed tool schema")

    with pytest.raises(InvalidRequestError):
        await with_retry(rejected, RetryPolicy(attempts=5), sleep=clock.sleep)

    assert attempts["n"] == 1
    assert clock.delays == []


async def test_the_last_failure_is_raised_once_attempts_run_out() -> None:
    clock = Clock()

    async def always_failing() -> str:
        raise ProviderUnavailableError("upstream is down")

    with pytest.raises(ProviderUnavailableError, match="upstream is down"):
        await with_retry(always_failing, RetryPolicy(attempts=3), sleep=clock.sleep)

    assert len(clock.delays) == 2


def test_backoff_grows_and_then_stops_growing() -> None:
    policy = RetryPolicy(base_delay_seconds=1.0, max_delay_seconds=4.0, jitter=False)
    assert [policy.delay_for(n) for n in (1, 2, 3, 4, 5)] == [1.0, 2.0, 4.0, 4.0, 4.0]


def test_jitter_stays_inside_the_backoff_window() -> None:
    # Without jitter, parallel employees hitting one rate limit retry in
    # lockstep and hit it again together.
    policy = RetryPolicy(base_delay_seconds=1.0, max_delay_seconds=4.0)
    assert all(0.0 <= policy.delay_for(3) <= 4.0 for _ in range(50))


async def test_the_adapter_retries_a_rate_limit_and_then_answers() -> None:
    responses = [
        httpx.Response(429, text="slow down"),
        httpx.Response(
            200,
            json={
                "model": "vendor/medium",
                "choices": [{"message": {"content": "Berlin."}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        ),
    ]
    adapter = OpenRouterProvider(
        "key",
        default_model="vendor/medium",
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda _r: responses.pop(0))),
        retry_policy=RetryPolicy(attempts=3, base_delay_seconds=0.0, jitter=False),
    )

    from domain.llm.models import LLMRequest, Message

    response = await adapter.generate(LLMRequest(messages=(Message.user("Which city?"),)))
    assert response.content == "Berlin."
    assert responses == []


async def test_the_fake_can_rehearse_a_retry_without_any_http() -> None:
    fake = FakeLLM([transient(), reply("Berlin.")])

    async def call() -> object:
        from domain.llm.models import LLMRequest, Message

        return await fake.generate(LLMRequest(messages=(Message.user("Which city?"),)))

    result = await with_retry(call, RetryPolicy(attempts=2, base_delay_seconds=0.0, jitter=False))
    assert result.content == "Berlin."
    assert fake.call_count == 2
