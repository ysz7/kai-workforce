"""The transcript is what makes a killed process resumable, so it is tested
as a persistence format, not as a convenience wrapper."""

from __future__ import annotations

from application.employee_runtime.transcript import RunState, Transcript
from domain.llm.models import Message, ToolCallRequest
from domain.tasks.plan import Observation


def test_a_transcript_round_trips_through_the_task_state() -> None:
    call = ToolCallRequest(id="c1", name="fs.read", arguments={"path": "a.txt"})
    transcript = (
        Transcript()
        .with_message(Message.system("be useful"), Message.user("read a.txt"))
        .with_message(Message.assistant("", tool_calls=(call,)))
        .with_message(Message.tool("contents", "c1"))
        .with_observation(Observation(step=0, summary="fs.read returned contents"))
        .with_spend(0.004)
        .advanced()
    )

    restored = Transcript.from_state(transcript.to_state())

    assert restored == transcript
    assert restored.messages[2].tool_calls[0].arguments == {"path": "a.txt"}
    assert restored.messages[3].tool_call_id == "c1"


def test_an_empty_state_produces_an_empty_transcript() -> None:
    assert Transcript.from_state(None) == Transcript()
    assert Transcript.from_state({}) == Transcript()


def test_spend_and_steps_accumulate_across_a_run() -> None:
    transcript = Transcript().with_spend(0.01).advanced().with_spend(0.02).advanced()
    assert transcript.cost_usd == 0.03
    assert transcript.steps == 2


def test_a_transcript_is_a_value_and_is_never_mutated() -> None:
    original = Transcript().with_message(Message.user("a"))
    extended = original.with_message(Message.user("b"))

    assert len(original.messages) == 1
    assert len(extended.messages) == 2


def test_run_state_carries_the_stage_a_restart_must_resume_into() -> None:
    state = RunState(
        stage="EXECUTING", attempt=2, verifier_feedback=("no sources",)
    ).to_state()
    restored = RunState.from_state(state)

    assert restored.stage == "EXECUTING"
    assert restored.attempt == 2
    assert restored.verifier_feedback == ("no sources",)
