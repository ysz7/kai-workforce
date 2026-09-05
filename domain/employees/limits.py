"""Budgets for one task.

An agent that loops does not usually fail loudly - it keeps working, keeps
calling models, and gets expensive well before anyone notices it is wrong. Every
run is therefore bounded on three axes at once, because each catches a different
failure: steps catch a loop, cost catches an expensive loop, and wall time
catches a slow one that is doing very little.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class LimitKind(StrEnum):
    STEPS = "STEPS"
    COST = "COST"
    WALL_TIME = "WALL_TIME"


@dataclass(frozen=True, slots=True)
class ExecutionLimits:
    max_steps: int = 12
    max_cost_usd: float = 1.0
    max_wall_time_seconds: float = 600.0

    def exceeded_by(
        self, *, steps: int, cost_usd: float, elapsed_seconds: float
    ) -> LimitKind | None:
        if steps >= self.max_steps:
            return LimitKind.STEPS
        if cost_usd >= self.max_cost_usd:
            return LimitKind.COST
        if elapsed_seconds >= self.max_wall_time_seconds:
            return LimitKind.WALL_TIME
        return None
