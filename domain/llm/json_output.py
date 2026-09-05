"""Getting structured data out of a model that was asked for it.

Models wrap JSON in prose and fences even when told not to, and a run should not
fail because of a code fence. So parsing is forgiving about packaging and strict
about content: if there is no object in there at all, that is a real failure and
it is reported as one.

It sits in the domain because both sides of the layer need it - the planner and
the verifier in `application/`, the screen reader in `infrastructure/` - and
those two may not import each other. It reads a string and returns a dict; there
is nothing in it that belongs to either side.
"""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_object(text: str) -> dict[str, Any] | None:
    """Pull the first JSON object out of a model reply, or return None."""
    for candidate in _candidates(text):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _candidates(text: str) -> list[str]:
    stripped = text.strip()
    found = [stripped, *(match.strip() for match in _FENCE.findall(stripped))]

    # Last resort: the outermost braces. Handles a model that explained itself
    # before answering.
    start, end = stripped.find("{"), stripped.rfind("}")
    if start != -1 and end > start:
        found.append(stripped[start : end + 1])
    return found
