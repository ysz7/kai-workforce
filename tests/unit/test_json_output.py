from __future__ import annotations

from domain.llm.json_output import extract_object


def test_plain_json_is_read() -> None:
    assert extract_object('{"passed": true}') == {"passed": True}


def test_a_fenced_block_is_unwrapped() -> None:
    # Models add fences even when told not to; failing a run over one would be
    # a bad trade.
    assert extract_object('```json\n{"steps": []}\n```') == {"steps": []}
    assert extract_object("```\n{\"a\": 1}\n```") == {"a": 1}


def test_json_after_an_explanation_is_still_found() -> None:
    text = 'Here is the plan you asked for:\n\n{"steps": [{"description": "go"}]}'
    assert extract_object(text) == {"steps": [{"description": "go"}]}


def test_text_with_no_object_returns_nothing() -> None:
    # Reported as a failure by the caller, rather than silently treated as empty.
    assert extract_object("I could not do that.") is None
    assert extract_object("") is None


def test_a_bare_array_is_not_an_object() -> None:
    assert extract_object("[1, 2, 3]") is None
