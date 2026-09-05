"""Credentials, and the rule that they never reach a model.

A key is resolved inside the tool that needs it, at the moment of the call. It
is never put in a prompt, an argument, a log line or a stored observation - so
the value type here refuses to print itself, and `redact` is applied to
everything that leaves a tool call for a log, the database or the transcript.

The wrapper is not security against the process itself: anything running here
can read the environment. It is protection against the realistic failure, which
is a secret being copied into a transcript, persisted, and then sent to a
provider on the next step.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

MASK = "***"

#: Argument names whose value never appears in a log, a record or a transcript.
SENSITIVE_NAMES = frozenset(
    {
        "api_key",
        "apikey",
        "access_token",
        "authorization",
        "credential",
        "credentials",
        "password",
        "passwd",
        "private_key",
        "secret",
        "token",
    }
)


@dataclass(frozen=True, slots=True)
class Secret:
    """A string that does not render itself.

    `str(secret)` is the mask, and so is its repr - the value comes out only
    through `reveal()`, which is easy to grep for in a review.
    """

    name: str
    _value: str

    def reveal(self) -> str:
        return self._value

    def __str__(self) -> str:
        return MASK

    def __repr__(self) -> str:
        return f"Secret({self.name!r}, {MASK})"


def is_sensitive(name: str) -> bool:
    lowered = name.lower()
    return any(marker in lowered for marker in SENSITIVE_NAMES)


def redact(value: Any) -> Any:
    """Mask secret-looking values anywhere in a nested structure."""
    if isinstance(value, Secret):
        return MASK
    if isinstance(value, dict):
        return {
            key: MASK if is_sensitive(str(key)) else redact(item) for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    return value
