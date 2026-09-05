"""The policy contract.

Phase 4 adds a minimal approval gate over a fixed list of irreversible actions;
Phase 10 grows this into a full engine with roles, risk and audit. The Protocol
is declared now so callers written earlier need no change when it arrives.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from domain.policies.models import Actor, PolicyDecision


@dataclass(frozen=True, slots=True)
class PolicyRequest:
    actor: Actor
    action: str
    tool: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


class PolicyEngine(Protocol):
    def evaluate(self, request: PolicyRequest) -> PolicyDecision: ...
