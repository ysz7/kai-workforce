"""Capabilities are the vocabulary of routing and permissions.

An employee declares what it needs; a model, a tool or another employee declares
what it offers. Nothing in the domain names a vendor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Capability(StrEnum):
    """A discrete ability a model, tool or employee can offer."""

    TEXT_REASONING = "TEXT_REASONING"
    LONG_CONTEXT = "LONG_CONTEXT"
    TOOL_CALLING = "TOOL_CALLING"
    STRUCTURED_OUTPUT = "STRUCTURED_OUTPUT"
    VISION = "VISION"
    CODE = "CODE"
    WEB_BROWSING = "WEB_BROWSING"
    COMPUTER_USE = "COMPUTER_USE"
    FILE_ACCESS = "FILE_ACCESS"
    EMAIL = "EMAIL"


@dataclass(frozen=True, slots=True)
class CapabilityRequirement:
    """What a piece of work needs in order to be routed somewhere."""

    required: frozenset[Capability] = field(default_factory=frozenset)
    preferred: frozenset[Capability] = field(default_factory=frozenset)
    min_context_tokens: int | None = None

    def is_satisfied_by(self, offered: frozenset[Capability]) -> bool:
        return self.required <= offered

    def score(self, offered: frozenset[Capability]) -> int:
        """How well an offer matches, used to rank candidates that all qualify."""
        if not self.is_satisfied_by(offered):
            return -1
        return len(self.preferred & offered)
