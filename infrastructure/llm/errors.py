"""Provider failures translated into the domain taxonomy.

This is the only place that knows an HTTP status code means anything. Above it,
callers see `RateLimitError` and decide what to do, not `httpx.HTTPStatusError`
and a number.
"""

from __future__ import annotations

import httpx

from domain.errors import (
    InvalidRequestError,
    ProviderError,
    ProviderUnavailableError,
    RateLimitError,
    TimeoutError,
)


def translate_status(status_code: int, body: str, *, provider: str) -> ProviderError:
    detail = body.strip()[:500] or "no response body"
    context = f"{provider} returned {status_code}: {detail}"

    if status_code == 429:
        return RateLimitError(context)
    if status_code in (408, 504):
        return TimeoutError(context)
    if status_code in (401, 403):
        # A rejected key is a configuration problem; retrying cannot fix it.
        return InvalidRequestError(context)
    if 400 <= status_code < 500:
        return InvalidRequestError(context)
    if status_code >= 500:
        return ProviderUnavailableError(context)
    return ProviderError(context)


def translate_transport_error(error: Exception, *, provider: str) -> ProviderError:
    if isinstance(error, httpx.TimeoutException):
        return TimeoutError(f"{provider} timed out: {error}")
    if isinstance(error, httpx.TransportError):
        return ProviderUnavailableError(f"{provider} is unreachable: {error}")
    return ProviderError(f"{provider} failed: {error}")
