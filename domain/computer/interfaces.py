"""The hierarchy of ways to reach the outside world, and how one is chosen.

The rule the product rests on: **use the most direct interface that exists.** An
API call is exact, cheap and verifiable; a click on a picture of a button is a
guess about a rendering. Computer Use is what makes the platform able to do
anything at all, and precisely for that reason it must be the last thing tried,
not the first.

Making that a sentence in a prompt would leave it unenforceable and invisible.
So the level is a property of the tool - declared on its `ToolSpec` - which
gives three things a sentence cannot:

- the choice is *made* from what the employee actually has, not hoped for;
- the choice is *logged* at the start of a run and recorded against every call,
  so a trace answers "why did it click instead of calling the API";
- turning a level off is a configuration change, and the levels below it keep
  working, which is Phase 5's Definition of Done.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum


class InterfaceLevel(StrEnum):
    """How an action reaches the world, best first."""

    #: A documented call with a defined result. Also where a local capability
    #: lives - the filesystem is an API, not a screen.
    API = "API"
    #: A service the platform speaks to on the user's behalf through a built
    #: integration rather than a raw endpoint.
    INTEGRATION = "INTEGRATION"
    #: The DOM: a real page, addressed by structure rather than by pixel.
    BROWSER = "BROWSER"
    #: Pixels, inside a surface the platform owns.
    COMPUTER_USE = "COMPUTER_USE"
    #: Pixels, on the user's own machine, where anything at all can be reached.
    DESKTOP = "DESKTOP"


#: Best to last resort. The order is the whole content of the rule.
PREFERENCE = (
    InterfaceLevel.API,
    InterfaceLevel.INTEGRATION,
    InterfaceLevel.BROWSER,
    InterfaceLevel.COMPUTER_USE,
    InterfaceLevel.DESKTOP,
)

_RANK = {level: index for index, level in enumerate(PREFERENCE)}

_WHY = {
    InterfaceLevel.API: "a direct call is exact and needs no screen",
    InterfaceLevel.INTEGRATION: "no direct API, but the platform speaks this service",
    InterfaceLevel.BROWSER: "no API path, and the page can be addressed by structure",
    InterfaceLevel.COMPUTER_USE: "nothing structured is reachable, so the screen it is",
    InterfaceLevel.DESKTOP: "the work is outside the browser and only the desktop reaches it",
}


def rank(level: InterfaceLevel) -> int:
    return _RANK[level]


@dataclass(frozen=True, slots=True)
class InterfaceChoice:
    """Which level a piece of work will be attempted at, and why."""

    level: InterfaceLevel
    reason: str
    available: tuple[InterfaceLevel, ...] = ()

    @property
    def is_last_resort(self) -> bool:
        return self.level in (InterfaceLevel.COMPUTER_USE, InterfaceLevel.DESKTOP)


def select(available: Iterable[InterfaceLevel]) -> InterfaceChoice | None:
    """The best of what is actually on hand. `None` when nothing is."""
    offered = tuple(sorted(set(available), key=rank))
    if not offered:
        return None
    best = offered[0]
    skipped = [level.value for level in PREFERENCE if rank(level) < rank(best)]
    reason = _WHY[best]
    if skipped:
        reason += f"; not available: {', '.join(skipped)}"
    return InterfaceChoice(level=best, reason=reason, available=offered)


def describe(available: Iterable[InterfaceLevel]) -> str:
    """The escalation rule, written from what this employee actually has.

    Put in front of the model so the ordering it is judged against is the same
    ordering it was told about.
    """
    offered = tuple(sorted(set(available), key=rank))
    if len(offered) < 2:
        return ""
    ladder = " then ".join(level.value for level in offered)
    return (
        f"You can reach the world at these levels, best first: {ladder}. "
        "Always try the most direct one that could work, and only step down a "
        "level once the one above it has actually failed - say which it was."
    )
