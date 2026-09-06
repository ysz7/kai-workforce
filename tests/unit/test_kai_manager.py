"""The manager, end to end, on scripted models and a workforce that never runs.

The Definition of Done for Phase 7 is a user stating a goal in one sentence and
getting a verified result without ever addressing an employee. These are that
sentence, taken apart: what KAI does with a request that needs no work, with one
that needs several people, with a result that does not meet what was asked, and
with a machine that has nobody to give work to.
"""

from __future__ import annotations

import json

from application.kai.delegation import CapabilityDelegator
from application.kai.intent import IntentReader
from application.kai.manager import KaiManager
from application.kai.planner import ObjectivePlanner
from application.kai.supervisor import Supervisor
from application.kai.synthesis import Synthesizer
from application.kai.verification import ObjectiveVerifier
from domain.workforce.protocols import ObjectiveStatus
from infrastructure.persistence.objective_repository import InMemoryObjectiveRepository
from infrastructure.persistence.plan_repository import InMemoryPlanRepository
from infrastructure.progress.broadcaster import InMemoryProgressBroadcaster
from tests.fakes.employees import definition
from tests.fakes.llm import FakeLLM, reply
from tests.fakes.workforce import FakeRegistry, RecordingExecution, failing

READER = definition("reader", tools=frozenset({"fs.read"}))
WRITER = definition("writer", tools=frozenset({"fs.write"}))


def intent(**overrides) -> str:
    return json.dumps(
        {
            "restatement": "do the thing",
            "constraints": {},
            "acceptance_criteria": ["the thing is done"],
            "needs_work": True,
            "answer": "",
            **overrides,
        }
    )


def plan(*goals: str, **extra) -> str:
    return json.dumps(
        {
            "rationale": "because",
            "tasks": [{"id": f"t{i}", "goal": goal} for i, goal in enumerate(goals)],
            **extra,
        }
    )


def verdict(passed: bool, *missing: str) -> str:
    return json.dumps(
        {"passed": passed, "reason": "checked", "missing": list(missing)}
    )


def build(
    *,
    script: list,
    delegation: list | None = None,
    workforce=(READER,),
    execution: RecordingExecution | None = None,
    progress: InMemoryProgressBroadcaster | None = None,
    objectives: InMemoryObjectiveRepository | None = None,
    plans: InMemoryPlanRepository | None = None,
    max_revisions: int = 2,
) -> tuple[KaiManager, RecordingExecution, InMemoryObjectiveRepository, InMemoryPlanRepository]:
    """One model for every stage, answering from a single script in order.

    Sharing the client is what makes the script readable as a story: read it,
    plan it, choose who, check it, write the answer.
    """
    llm = FakeLLM([reply(item) if isinstance(item, str) else item for item in script])
    # Delegation gets its own client when more than one employee is declared, so
    # that "who should do this" does not have to be interleaved into the story
    # above at whatever point the supervisor happens to ask.
    chooser = FakeLLM([reply(item) for item in delegation or ()]) if delegation else llm
    registry = FakeRegistry(*workforce)
    runs = execution or RecordingExecution()
    objective_store = objectives or InMemoryObjectiveRepository()
    plan_store = plans or InMemoryPlanRepository()
    manager = KaiManager(
        intent=IntentReader(llm),
        planner=ObjectivePlanner(llm),
        supervisor=Supervisor(
            execution=runs,
            delegator=CapabilityDelegator(chooser, registry),
            max_attempts=1,
        ),
        verifier=ObjectiveVerifier(llm),
        synthesizer=Synthesizer(llm),
        registry=registry,
        objectives=objective_store,
        plans=plan_store,
        progress=progress or InMemoryProgressBroadcaster(),
        max_revisions=max_revisions,
    )
    return manager, runs, objective_store, plan_store


# --- The happy path -----------------------------------------------------------


async def test_one_sentence_becomes_a_verified_answer() -> None:
    manager, execution, objectives, plans = build(
        script=[
            intent(),
            plan("Read the notes"),
            verdict(True),
            "The notes say the answer is 41.",
        ]
    )

    objective = await manager.receive("Tell me what the notes say")
    result = await manager.handle_objective(objective)

    assert result.status is ObjectiveStatus.DONE
    assert result.summary == "The notes say the answer is 41."
    assert execution.goals == ["Read the notes"]

    # And it is all on the record: the objective, its reading, its plan.
    stored = await objectives.get(objective.id)
    assert stored is not None and stored.status is ObjectiveStatus.DONE
    assert stored.acceptance_criteria == ("the thing is done",)
    assert stored.result is not None and stored.result.summary == result.summary
    assert stored.text == "Tell me what the notes say", "the user's words are kept verbatim"

    revisions = await plans.for_objective(objective.id)
    assert [p.revision for p in revisions] == [1]
    assert revisions[0].status.value == "DONE"


async def test_the_answer_carries_the_evidence_behind_it() -> None:
    manager, _, _, _ = build(
        script=[intent(), plan("Read it", "Write it"), verdict(True), "Done."],
        # Two employees means the delegator asks, and two tasks means twice.
        delegation=[json.dumps({"employee": "reader"}), json.dumps({"employee": "writer"})],
        workforce=(READER, WRITER),
    )

    result = await manager.handle_objective(await manager.receive("Do two things"))

    assert result.output["delegated"] is True
    assert [task["employee"] for task in result.output["tasks"]] == ["reader", "writer"]
    assert result.output["completed"] == 2
    assert result.cost_usd > 0


# --- Not everything needs the workforce (§7.5) --------------------------------


async def test_a_question_is_answered_without_a_plan_or_an_employee() -> None:
    manager, execution, _, plans = build(
        script=[intent(needs_work=False, answer="It keeps the database in one file.")]
    )

    result = await manager.handle_objective(await manager.receive("What is SQLite?"))

    assert result.status is ObjectiveStatus.DONE
    assert result.summary == "It keeps the database in one file."
    assert execution.started == [], "nobody was given work"
    assert await plans.for_objective(result.objective_id) == [], "and nothing was decomposed"
    assert result.output["delegated"] is False


# --- When it does not meet what was asked -------------------------------------


async def test_a_rejected_result_is_replanned_once_and_then_escalated() -> None:
    manager, execution, _, plans = build(
        script=[
            intent(),
            plan("Find twenty things"),
            verdict(False, "only eleven were found"),
            plan("Find twenty things, properly"),
            verdict(False, "only eleven were found"),
            "Here are the eleven I found.",
        ]
    )

    result = await manager.handle_objective(await manager.receive("Find twenty things"))

    assert result.status is ObjectiveStatus.ESCALATED
    assert result.missing == ("only eleven were found",)
    assert "eleven" in result.summary
    assert len(execution.started) == 2, "it was planned and run twice, not more"

    revisions = await plans.for_objective(result.objective_id)
    assert [p.revision for p in revisions] == [2, 1]
    assert revisions[1].status.value == "SUPERSEDED", "the first plan is kept, not overwritten"


async def test_the_second_plan_is_told_what_the_first_one_missed() -> None:
    manager, _, _, _ = build(
        script=[
            intent(),
            plan("Find twenty things"),
            verdict(False, "only eleven were found"),
            plan("Find nine more"),
            verdict(True),
            "Twenty things.",
        ]
    )

    result = await manager.handle_objective(await manager.receive("Find twenty things"))

    assert result.status is ObjectiveStatus.DONE


async def test_work_that_failed_is_still_handed_over_with_what_is_missing() -> None:
    """Escalation is not failure with a nicer name (§7.11)."""
    manager, _, objectives, _ = build(
        script=[
            intent(),
            plan("Fetch the source"),
            verdict(False, "nothing was fetched"),
            plan("Fetch the source again"),
            verdict(False, "nothing was fetched"),
            "I could not fetch anything.",
        ],
        execution=RecordingExecution(failing()),
    )

    result = await manager.handle_objective(await manager.receive("Fetch it"))

    assert result.status is ObjectiveStatus.ESCALATED
    assert result.missing == ("nothing was fetched",)
    stored = await objectives.get(result.objective_id)
    assert stored is not None and stored.finished_at is not None


async def test_nobody_to_delegate_to_is_escalated_not_replanned() -> None:
    """Every plan would end in the same place, so a second one is waste."""
    manager, _, _, plans = build(
        script=[intent(), plan("Do it")], workforce=()
    )

    result = await manager.handle_objective(await manager.receive("Do it"))

    assert result.status is ObjectiveStatus.ESCALATED
    assert "employees/" in result.summary
    assert len(await plans.for_objective(result.objective_id)) == 1


# --- What the interface sees --------------------------------------------------


async def test_the_manager_announces_its_own_progress() -> None:
    progress = InMemoryProgressBroadcaster()
    manager, _, _, _ = build(
        script=[intent(), plan("Read it"), verdict(True), "Done."], progress=progress
    )

    objective = await manager.receive("Read the notes")
    await manager.handle_objective(objective)

    events = progress.recent(objective.id)
    kinds = [event.kind.value for event in events]
    assert kinds[0] == "STAGE"
    assert "PLAN" in kinds
    assert kinds[-1] == "RESULT"
    assert all(event.objective_id == objective.id for event in events)
    # The plan event names the tasks, which is how a watcher learns to follow them.
    planned = next(event for event in events if event.kind.value == "PLAN")
    assert planned.payload["tasks"] and planned.payload["tasks"][0]["goal"] == "Read it"


# --- What the first real run of this phase taught -----------------------------


async def test_a_verdict_that_passes_while_naming_something_missing_does_not_pass() -> None:
    """Found in the validation run: the model said yes and listed a gap.

    Reading it either way is a choice, so it is read the safe way - the list is
    the more specific claim, and the one a second attempt can act on.
    """
    manager, _, _, _ = build(
        script=[
            intent(),
            plan("Do it"),
            json.dumps({"passed": True, "reason": "looks fine", "missing": ["the count"]}),
            plan("Do it properly"),
            verdict(True),
            "Done properly.",
        ]
    )

    result = await manager.handle_objective(await manager.receive("Do it"))

    assert result.status is ObjectiveStatus.DONE, "it replanned rather than shipping the gap"
    assert result.summary == "Done properly."


async def test_a_verdict_saying_nothing_is_missing_is_not_a_contradiction() -> None:
    """A model that writes "none" is agreeing with itself, not disagreeing."""
    manager, execution, _, _ = build(
        script=[
            intent(),
            plan("Do it"),
            json.dumps({"passed": True, "reason": "fine", "missing": ["none", "  "]}),
            "Done.",
        ]
    )

    result = await manager.handle_objective(await manager.receive("Do it"))

    assert result.status is ObjectiveStatus.DONE
    assert len(execution.started) == 1, "it was not replanned"


async def test_with_no_criteria_the_request_itself_becomes_the_standard() -> None:
    """Also from the validation run: a weak reading must not switch the check off.

    Passing by default when no criteria were written down would make KAI's own
    verification a no-op exactly when comprehension had been weakest.
    """
    manager, _, _, _ = build(
        script=[
            intent(acceptance_criteria=[]),
            plan("Do it"),
            verdict(False, "it did not answer the question that was asked"),
            plan("Do it properly"),
            verdict(False, "it did not answer the question that was asked"),
            "Here is what I managed.",
        ]
    )

    result = await manager.handle_objective(await manager.receive("Answer my question"))

    assert result.status is ObjectiveStatus.ESCALATED
    assert result.missing == ("it did not answer the question that was asked",)
