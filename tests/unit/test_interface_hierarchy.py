"""The escalation rule, which is a product decision before it is a code path.

Computer Use is what makes the platform able to do anything, and that is exactly
why it has to be the last thing tried. These check that the ordering is real -
decided from what an employee actually has, and visible afterwards.
"""

from __future__ import annotations

from domain.computer.interfaces import InterfaceLevel, describe, select
from domain.tools.models import ToolSpec


def test_the_most_direct_available_interface_wins() -> None:
    choice = select(
        [InterfaceLevel.DESKTOP, InterfaceLevel.BROWSER, InterfaceLevel.API]
    )

    assert choice is not None
    assert choice.level is InterfaceLevel.API
    assert not choice.is_last_resort


def test_a_screen_is_chosen_only_when_nothing_better_exists() -> None:
    choice = select([InterfaceLevel.COMPUTER_USE, InterfaceLevel.DESKTOP])

    assert choice is not None
    assert choice.level is InterfaceLevel.COMPUTER_USE
    assert choice.is_last_resort
    # The reason says what was missing, not only what was picked: that is the
    # half of the trace a person actually reads.
    assert "API" in choice.reason and "BROWSER" in choice.reason


def test_nothing_available_is_not_a_choice() -> None:
    assert select([]) is None


def test_a_tool_reaches_the_world_through_a_direct_call_unless_it_says_otherwise() -> None:
    """The default has to be the safe one: a new tool is not a screen driver."""
    spec = ToolSpec.of("fs.read", "Read a file.")

    assert spec.interface_level is InterfaceLevel.API


def test_the_ladder_is_described_only_when_there_is_a_choice_to_make() -> None:
    assert describe([InterfaceLevel.API]) == ""
    ladder = describe([InterfaceLevel.COMPUTER_USE, InterfaceLevel.BROWSER])
    assert "BROWSER then COMPUTER_USE" in ladder
