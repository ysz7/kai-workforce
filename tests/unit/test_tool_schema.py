"""Parameters declared once: the schema the model sees and the check on the way back."""

from __future__ import annotations

import pytest

from domain.errors import ToolInputError
from domain.tools.models import ToolSpec
from domain.tools.schema import Param, ParameterSet


def params(*items: Param) -> ParameterSet:
    return ParameterSet(items)


def test_the_schema_a_model_is_shown_is_generated_from_the_declaration() -> None:
    spec = ToolSpec.of(
        "fs.read",
        "Read a file.",
        Param("path", description="Where."),
        Param("offset", type="integer", required=False, default=0),
    )

    assert spec.json_schema == {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Where."},
            "offset": {"type": "integer", "default": 0},
        },
        "required": ["path"],
        "additionalProperties": False,
    }


def test_a_missing_required_argument_is_reported_by_name() -> None:
    with pytest.raises(ToolInputError, match="path"):
        params(Param("path")).validate({})


def test_an_optional_argument_falls_back_to_its_default() -> None:
    cleaned = params(Param("limit", type="integer", required=False, default=5)).validate({})
    assert cleaned == {"limit": 5}


def test_an_argument_the_tool_does_not_have_is_dropped_and_named() -> None:
    """A spurious key next to a correct call is clumsiness, not a wrong call.

    Refusing the whole call over it costs a step and teaches nothing; the
    dropped names are reported back instead.
    """
    parameters = params(Param("path"))
    sent = {"path": "a.txt", "cursor": 0}

    assert parameters.validate(sent) == {"path": "a.txt"}
    assert parameters.unknown(sent) == ["cursor"]


@pytest.mark.parametrize(
    ("declared", "sent", "expected"),
    [
        ("integer", "3", 3),
        ("number", "1.5", 1.5),
        ("boolean", "yes", True),
        ("boolean", "false", False),
        ("array", "one", ["one"]),
        ("string", 7, "7"),
    ],
)
def test_types_a_model_gets_slightly_wrong_are_coerced(declared, sent, expected) -> None:
    """Refusing "3" for an integer costs a step and teaches the model nothing."""
    cleaned = params(Param("value", type=declared)).validate({"value": sent})
    assert cleaned == {"value": expected}


def test_a_value_that_is_not_the_declared_type_at_all_is_refused() -> None:
    with pytest.raises(ToolInputError, match="integer"):
        params(Param("value", type="integer")).validate({"value": "not a number"})


def test_an_enum_is_enforced() -> None:
    parameter = Param("mode", enum=("append", "replace"))
    assert params(parameter).validate({"mode": "append"}) == {"mode": "append"}
    with pytest.raises(ToolInputError, match="append"):
        params(parameter).validate({"mode": "delete"})


def test_a_parameter_cannot_declare_a_type_json_schema_does_not_have() -> None:
    with pytest.raises(ValueError, match="not a JSON Schema type"):
        Param("value", type="date")


def test_an_optional_argument_left_blank_falls_back_to_its_default() -> None:
    """Models fill in the blank they were shown; "" there means "no value"."""
    cleaned = params(Param("pattern", required=False, default="*")).validate({"pattern": ""})
    assert cleaned == {"pattern": "*"}


def test_a_required_argument_may_legitimately_be_empty() -> None:
    # Writing an empty file is a real thing to ask for.
    assert params(Param("content")).validate({"content": ""}) == {"content": ""}
