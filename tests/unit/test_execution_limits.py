from __future__ import annotations

from domain.employees.limits import ExecutionLimits, LimitKind


def test_a_run_inside_every_budget_is_not_stopped() -> None:
    limits = ExecutionLimits(max_steps=5, max_cost_usd=1.0, max_wall_time_seconds=60)
    assert limits.exceeded_by(steps=2, cost_usd=0.3, elapsed_seconds=10) is None


def test_each_budget_catches_a_different_failure() -> None:
    limits = ExecutionLimits(max_steps=5, max_cost_usd=1.0, max_wall_time_seconds=60)

    # A loop.
    assert limits.exceeded_by(steps=5, cost_usd=0, elapsed_seconds=0) is LimitKind.STEPS
    # An expensive loop.
    assert limits.exceeded_by(steps=0, cost_usd=1.0, elapsed_seconds=0) is LimitKind.COST
    # A slow one doing very little.
    assert (
        limits.exceeded_by(steps=0, cost_usd=0, elapsed_seconds=60) is LimitKind.WALL_TIME
    )


def test_steps_are_reported_before_cost_when_both_are_spent() -> None:
    # Only one reason is reported; the cheapest to explain comes first.
    limits = ExecutionLimits(max_steps=1, max_cost_usd=0.1, max_wall_time_seconds=1)
    assert limits.exceeded_by(steps=9, cost_usd=9.0, elapsed_seconds=9) is LimitKind.STEPS
