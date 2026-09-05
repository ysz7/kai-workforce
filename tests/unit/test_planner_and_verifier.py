from __future__ import annotations

import pytest

from application.employee_runtime.planner import Planner
from application.employee_runtime.verifier import Verifier
from domain.errors import PlanningError
from domain.tasks.plan import TaskPlan
from domain.tasks.task import Task, TaskResult
from tests.fakes.employees import definition
from tests.fakes.llm import FakeLLM, reply

PLAN_JSON = """```json
{
  "rationale": "Two steps are enough.",
  "steps": [
    {"description": "Collect what is known", "expected_outcome": "at least three named sources"},
    {"description": "Write it up", "expected_outcome": "a paragraph with citations"}
  ]
}
```"""


async def test_a_plan_is_parsed_out_of_a_fenced_reply() -> None:
    planner = Planner(FakeLLM([reply(PLAN_JSON)]))
    plan = await planner.plan(Task.create("Explain WAL mode"), definition())

    assert len(plan.steps) == 2
    assert plan.steps[0].description == "Collect what is known"
    assert plan.steps[0].expected_outcome == "at least three named sources"
    assert plan.rationale == "Two steps are enough."


async def test_the_plan_prompt_names_the_role_the_goal_and_the_tools() -> None:
    llm = FakeLLM([reply(PLAN_JSON)])
    await planner_plan(llm)

    prompt = llm.last_request.messages[0].content
    assert "Research Specialist" in prompt
    assert "Explain WAL mode" in prompt
    assert "none" in prompt, "an employee with no tools must be told so"


async def planner_plan(llm) -> TaskPlan:
    return await Planner(llm).plan(Task.create("Explain WAL mode"), definition())


async def test_an_over_long_plan_is_truncated_to_the_limit() -> None:
    steps = ", ".join(f'{{"description": "step {i}"}}' for i in range(20))
    planner = Planner(FakeLLM([reply(f'{{"steps": [{steps}]}}')]), max_steps=4)

    plan = await planner.plan(Task.create("Do a lot"), definition())
    assert len(plan.steps) == 4


async def test_unparseable_planner_output_is_a_planning_error() -> None:
    planner = Planner(FakeLLM([reply("I would rather not.")]))
    with pytest.raises(PlanningError, match="no usable JSON"):
        await planner.plan(Task.create("Explain WAL mode"), definition())


async def test_a_plan_with_no_usable_steps_is_a_planning_error() -> None:
    planner = Planner(FakeLLM([reply('{"steps": [{"description": "   "}]}')]))
    with pytest.raises(PlanningError, match="no steps"):
        await planner.plan(Task.create("Explain WAL mode"), definition())


# --- Verifier -----------------------------------------------------------------


async def test_a_good_result_passes() -> None:
    verifier = Verifier(FakeLLM([reply('{"passed": true, "reason": "sources given"}')]))
    verdict = await verifier.verify(
        Task.create("Explain WAL mode"), TaskResult(summary="WAL works like this, per [1].")
    )

    assert verdict.passed
    assert verdict.reason == "sources given"


async def test_a_thin_result_is_rejected_with_what_is_missing() -> None:
    verifier = Verifier(
        FakeLLM(
            [
                reply(
                    '{"passed": false, "reason": "no sources",'
                    ' "missing": ["named sources", "dates"]}'
                )
            ]
        )
    )
    verdict = await verifier.verify(
        Task.create("Explain WAL mode"), TaskResult(summary="It is faster.")
    )

    assert not verdict.passed
    assert verdict.missing == ("named sources", "dates")


async def test_an_empty_result_is_rejected_without_asking_a_model() -> None:
    llm = FakeLLM([])
    verdict = await Verifier(llm).verify(
        Task.create("Explain WAL mode"), TaskResult(summary="   ")
    )

    assert not verdict.passed
    assert llm.call_count == 0, "nothing is not an answer; no call needed to know it"


async def test_an_unreadable_verdict_does_not_wave_the_work_through() -> None:
    # Success is never assumed. A verifier that cannot be parsed is a failure to
    # verify, not a pass.
    verifier = Verifier(FakeLLM([reply("Looks fine to me!")]))
    verdict = await verifier.verify(
        Task.create("Explain WAL mode"), TaskResult(summary="Something.")
    )

    assert not verdict.passed


async def test_the_verifier_is_shown_the_plan_it_should_judge_against() -> None:
    llm = FakeLLM([reply('{"passed": true}')])
    await Verifier(llm).verify(
        Task.create("Explain WAL mode"),
        TaskResult(summary="Done."),
        TaskPlan.of("collect sources"),
    )

    prompt = llm.last_request.messages[0].content
    assert "collect sources" in prompt
    assert "Explain WAL mode" in prompt
