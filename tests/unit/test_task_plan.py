from __future__ import annotations

from domain.tasks.plan import Observation, PlanStep, TaskPlan


def test_a_plan_tracks_the_next_unfinished_step() -> None:
    plan = TaskPlan.of("gather", "compare", "write")
    assert plan.next_step.description == "gather"

    plan = plan.complete_through(0)
    assert plan.next_step.description == "compare"


def test_completing_a_step_completes_the_ones_before_it() -> None:
    # A model that reports finishing step 3 has finished 1 and 2 in practice;
    # tracking them separately produces a plan that never completes.
    plan = TaskPlan.of("a", "b", "c").complete_through(1)
    assert [step.done for step in plan.steps] == [True, True, False]


def test_a_finished_plan_has_no_next_step() -> None:
    assert TaskPlan.of("a").complete_through(0).next_step is None


def test_an_empty_plan_says_so() -> None:
    assert TaskPlan().is_empty
    assert not TaskPlan.of("a").is_empty


def test_a_plan_round_trips_through_storage() -> None:
    plan = TaskPlan(
        steps=(PlanStep(0, "gather", "at least three sources", done=True),),
        rationale="because",
    )
    restored = TaskPlan.from_dict(plan.to_dict())

    assert restored == plan


def test_no_plan_stays_no_plan() -> None:
    assert TaskPlan.from_dict(None) is None
    assert TaskPlan.from_dict({}) is None


def test_an_observation_round_trips() -> None:
    observation = Observation(step=2, summary="found nothing", succeeded=False)
    assert Observation.from_dict(observation.to_dict()) == observation
