"""Tool parameters, declared once and rendered as JSON Schema for the model.

A tool author writes `Param("path", description="...")` and gets three things
from it: the schema the model is shown, the validation of what the model sent
back, and the documentation a human reads. Writing the schema by hand instead
would let those three drift apart, and the first sign of that is a model that
keeps calling a tool wrong for reasons nobody can see.

Validation is forgiving where a model is merely clumsy and strict where it is
actually wrong. Models send `"3"` for an integer, and they garnish a correct
call with keys from some other harness - `cursor`, `loc` - often enough that
throwing the call away over them burns a run's budget on nothing. Observed with
a 20B local model: half of a twelve-step budget went on rejected calls whose
required arguments were all present and correct.

So: types are coerced, unknown arguments are dropped and *reported* in the
result rather than silently swallowed, and a missing required argument is a real
mistake that comes back as one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from domain.errors import ToolInputError

JSON_TYPES = frozenset({"string", "integer", "number", "boolean", "array", "object"})


@dataclass(frozen=True, slots=True)
class Param:
    """One argument of a tool, in the terms JSON Schema understands."""

    name: str
    type: str = "string"
    description: str = ""
    required: bool = True
    default: Any = None
    enum: tuple[str, ...] = ()
    #: Only meaningful when `type` is "array".
    item_type: str = "string"

    def __post_init__(self) -> None:
        if self.type not in JSON_TYPES:
            raise ValueError(f"{self.name}: '{self.type}' is not a JSON Schema type")

    def to_schema(self) -> dict[str, Any]:
        schema: dict[str, Any] = {"type": self.type}
        if self.description:
            schema["description"] = self.description
        if self.enum:
            schema["enum"] = list(self.enum)
        if self.type == "array":
            schema["items"] = {"type": self.item_type}
        if self.default is not None:
            schema["default"] = self.default
        return schema


@dataclass(frozen=True, slots=True)
class ParameterSet:
    """The parameters of one tool: schema on the way out, checks on the way in."""

    params: tuple[Param, ...] = field(default_factory=tuple)

    def example(self) -> str:
        """The call shape, as one line to put in a failure message.

        A model that got the argument names wrong does better with the shape it
        should have sent than with a list of what it sent wrong.
        """
        rendered = ", ".join(
            f'"{param.name}": <{param.type}>' for param in self.params if param.required
        )
        return "{" + rendered + "}"

    def to_json_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {param.name: param.to_schema() for param in self.params},
            "required": [param.name for param in self.params if param.required],
            "additionalProperties": False,
        }

    def unknown(self, input_data: dict[str, Any]) -> list[str]:
        """Arguments this tool does not have. Dropped, but never in silence."""
        return sorted(set(input_data) - {param.name for param in self.params})

    def validate(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Check and coerce what the model sent. Raises `ToolInputError`."""
        cleaned: dict[str, Any] = {}
        for param in self.params:
            value = input_data.get(param.name)
            # An optional argument sent as "" is a model filling in the blank it
            # was shown rather than omitting it, and it means "no value".
            missing = param.name not in input_data or value is None or (
                value == "" and not param.required
            )
            if missing:
                if param.required:
                    raise ToolInputError(f"Missing required argument '{param.name}'")
                if param.default is not None:
                    cleaned[param.name] = param.default
                continue
            cleaned[param.name] = _coerce(param, value)
        return cleaned


def _coerce(param: Param, value: Any) -> Any:
    try:
        coerced = _convert(param, value)
    except (TypeError, ValueError) as error:
        raise ToolInputError(
            f"Argument '{param.name}' should be a {param.type}, got {value!r}"
        ) from error
    if param.enum and str(coerced) not in param.enum:
        raise ToolInputError(
            f"Argument '{param.name}' must be one of {', '.join(param.enum)}, got {coerced!r}"
        )
    return coerced


def _convert(param: Param, value: Any) -> Any:
    match param.type:
        case "string":
            return value if isinstance(value, str) else str(value)
        case "integer":
            return value if isinstance(value, int) and not isinstance(value, bool) else int(value)
        case "number":
            return float(value)
        case "boolean":
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                lowered = value.strip().lower()
                if lowered in {"true", "yes", "1"}:
                    return True
                if lowered in {"false", "no", "0"}:
                    return False
            raise ValueError(value)
        case "array":
            if isinstance(value, str):
                # A model asked for a list often sends one item as a bare string.
                return [value]
            if not isinstance(value, list):
                raise TypeError(value)
            return value
        case _:
            if not isinstance(value, dict):
                raise TypeError(value)
            return value
