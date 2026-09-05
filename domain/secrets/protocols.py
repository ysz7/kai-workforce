from __future__ import annotations

from typing import Protocol

from domain.secrets.models import Secret


class SecretResolver(Protocol):
    """Where a tool gets a credential from, at the moment it needs one.

    Tools are handed the resolver, never the value: a tool built at start-up
    with a key baked into it puts that key in every trace of its construction.
    """

    def get(self, name: str) -> Secret: ...

    def maybe(self, name: str) -> Secret | None: ...
