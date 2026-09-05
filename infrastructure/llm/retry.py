"""Exponential backoff for transient failures only.

Retrying a rejected request just spends the budget again and arrives at the same
answer, so only errors that declare themselves transient are retried.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from domain.errors import ProviderError
from infrastructure.observability.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    attempts: int = 3
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 8.0
    #: Full jitter. Without it, several parallel employees hitting the same rate
    #: limit retry in lockstep and hit it again together.
    jitter: bool = True

    def delay_for(self, attempt: int) -> float:
        delay = min(self.base_delay_seconds * (2 ** (attempt - 1)), self.max_delay_seconds)
        return random.uniform(0, delay) if self.jitter else delay


async def with_retry[T](
    operation: Callable[[], Awaitable[T]],
    policy: RetryPolicy | None = None,
    *,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    policy = policy or RetryPolicy()
    last_error: ProviderError | None = None

    for attempt in range(1, policy.attempts + 1):
        try:
            return await operation()
        except ProviderError as error:
            if not error.transient or attempt == policy.attempts:
                raise
            last_error = error
            delay = policy.delay_for(attempt)
            log.warning(
                "llm.retry",
                attempt=attempt,
                of=policy.attempts,
                delay_seconds=round(delay, 3),
                error=type(error).__name__,
            )
            await sleep(delay)

    raise last_error  # pragma: no cover - the loop either returns or raises
