"""Reading a screen: the part of Computer Use that is actually hard.

The tests that matter here are the ones about *not* trusting the answer. A model
that invented a coordinate looks exactly like one that read it off the screen,
and the only defence is to check the answer against the picture it was given.
"""

from __future__ import annotations

import json

from application.computer.screen_reader import LLMScreenReader
from domain.capabilities.models import Capability
from domain.computer.models import Screenshot
from tests.fakes.computer import png_bytes
from tests.fakes.llm import FakeLLM


def a_screenshot(width: int = 1280, height: int = 800) -> Screenshot:
    return Screenshot(image=png_bytes(), width=width, height=height)


def answering(payload: dict[str, object]) -> FakeLLM:
    return FakeLLM.answering(json.dumps(payload))


async def test_the_screenshot_is_sent_as_a_picture_not_described_in_words() -> None:
    llm = answering({"answer": "A search page.", "targets": []})

    await LLMScreenReader(llm).read(a_screenshot(), "what is this?")

    message = llm.last_request.messages[0]
    assert len(message.images) == 1
    assert message.images[0].data_url.startswith("data:image/png;base64,")


async def test_the_model_is_told_the_frame_its_coordinates_have_to_be_in() -> None:
    """A coordinate means nothing without the size of the thing it indexes."""
    llm = answering({"answer": "ok", "targets": []})

    await LLMScreenReader(llm).read(a_screenshot(1024, 768), "where is search?")

    prompt = llm.last_request.messages[0].content
    assert "1024" in prompt and "768" in prompt


async def test_targets_come_back_as_coordinates() -> None:
    llm = answering(
        {
            "answer": "A toolbar across the top.",
            "targets": [{"label": "Save", "x": 100, "y": 40, "confidence": 0.8}],
        }
    )

    view = await LLMScreenReader(llm).read(a_screenshot(), "where is save?")

    assert view.targets[0].label == "Save"
    assert (view.targets[0].x, view.targets[0].y) == (100, 40)


async def test_a_target_outside_the_picture_is_dropped_rather_than_clamped() -> None:
    """A clamped coordinate still points at something, and at the wrong thing."""
    llm = answering(
        {"answer": "ok", "targets": [{"label": "Save", "x": 5000, "y": 40}]}
    )

    view = await LLMScreenReader(llm).read(a_screenshot(1280, 800), "where is save?")

    assert view.targets == ()


async def test_a_malformed_target_does_not_take_the_readable_ones_with_it() -> None:
    llm = answering(
        {
            "answer": "ok",
            "targets": [
                {"label": "broken"},
                "not a target",
                {"label": "Save", "x": 10, "y": 10},
            ],
        }
    )

    view = await LLMScreenReader(llm).read(a_screenshot(), "?")

    assert [t.label for t in view.targets] == ["Save"]


async def test_an_unreadable_answer_is_reported_rather_than_guessed_at() -> None:
    llm = FakeLLM.answering("I had a look and it seems fine, honestly")

    view = await LLMScreenReader(llm).read(a_screenshot(), "?")

    assert view.targets == ()
    assert "could not be read" in view.answer


async def test_a_confirmation_that_cannot_be_read_is_a_no() -> None:
    """Otherwise a run treats "I could not tell" as "it worked"."""
    llm = FakeLLM.answering("probably!")

    view = await LLMScreenReader(llm).confirm(a_screenshot(), "the dialog is open")

    assert view.confirmed is False


async def test_a_confirmation_answers_the_question_it_was_asked() -> None:
    llm = answering({"answer": "The dialog is open.", "confirmed": True, "targets": []})

    view = await LLMScreenReader(llm).confirm(a_screenshot(), "the dialog is open")

    assert view.confirmed is True
    assert "the dialog is open" in llm.last_request.messages[0].content


async def test_confidence_that_is_not_a_number_does_not_fail_the_read() -> None:
    llm = answering(
        {"answer": "ok", "targets": [{"label": "Save", "x": 1, "y": 1, "confidence": "high"}]}
    )

    view = await LLMScreenReader(llm).read(a_screenshot(), "?")

    assert view.targets[0].confidence == 0.0


def test_reading_a_screen_asks_the_router_for_eyes_and_names_no_model() -> None:
    _, requirement, _ = LLMScreenReader.routing()

    assert Capability.VISION in requirement.required
