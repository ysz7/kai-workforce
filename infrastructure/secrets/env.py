"""Credentials come from the environment, and are read at the moment of use.

Local-first means there is no vault to talk to: the machine's own environment
is the store. What matters is *when* the value is read. Resolving a key when a
tool is constructed puts it in the container, in every repr of that container
and in whatever a debugger or a crash report prints. Resolving it inside the
call keeps its lifetime to the call.

`KAI_SECRET_<NAME>` is checked first so a credential can be scoped to this
platform, with the plain name as a fallback for the variables a user already has
set for other tools.
"""

from __future__ import annotations

import os

from domain.errors import SecretNotFoundError
from domain.secrets.models import Secret

PREFIX = "KAI_SECRET_"


class EnvSecretResolver:
    """Implements `domain.secrets.protocols.SecretResolver`."""

    def __init__(self, environ: dict[str, str] | None = None) -> None:
        self._environ = environ if environ is not None else os.environ  # type: ignore[assignment]

    def maybe(self, name: str) -> Secret | None:
        key = name.upper()
        for candidate in (f"{PREFIX}{key}", key):
            value = self._environ.get(candidate)
            if value:
                return Secret(name=name, _value=value)
        return None

    def get(self, name: str) -> Secret:
        secret = self.maybe(name)
        if secret is None:
            raise SecretNotFoundError(
                f"No credential named '{name}'. Set {PREFIX}{name.upper()} in the environment."
            )
        return secret
