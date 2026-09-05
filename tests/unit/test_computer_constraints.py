"""The bounds on the one capability that can reach anything.

`Workspace` confines the filesystem tools to a directory; this is the same idea
for a screen, and it is checked with the same suspicion: the interesting cases
are the ones where a refusal has to happen even though nothing looks wrong.
"""

from __future__ import annotations

import pytest

from domain.computer.constraints import ComputerConstraints
from domain.computer.models import ComputerAction, Region, Surface
from domain.errors import PermissionDeniedError, StopRequestedError
from infrastructure.computer.guarded import GuardedComputer
from tests.fakes.computer import EngagedStop, FakeComputer

BROWSER = ComputerConstraints(applies_to_applications=False)


def desktop(**extra: object) -> ComputerConstraints:
    return ComputerConstraints(
        allowed_applications=frozenset({"Preview"}),
        applies_to_applications=True,
        **extra,  # type: ignore[arg-type]
    )


# --- The region ---------------------------------------------------------------


async def test_a_click_outside_the_allowed_region_is_refused_not_asked_about() -> None:
    computer = FakeComputer()
    guard = GuardedComputer(
        computer, ComputerConstraints(allowed_region=Region(0, 0, 100, 100),
                                      applies_to_applications=False)
    )

    with pytest.raises(PermissionDeniedError, match="outside the part of the screen"):
        await guard.click(500, 500)

    assert computer.actions == []


async def test_the_region_is_clipped_to_the_screen_that_turned_out_to_be_there() -> None:
    """A region set for a bigger display must not refuse every visible click."""
    computer = FakeComputer(width=800, height=600)
    guard = GuardedComputer(
        computer,
        ComputerConstraints(
            allowed_region=Region(0, 0, 4000, 3000), applies_to_applications=False
        ),
    )

    await guard.screenshot()
    await guard.click(400, 300)

    assert guard.constraints.allowed_region == Region(0, 0, 800, 600)
    assert computer.names() == ["screenshot", "click"]


# --- The application ----------------------------------------------------------


async def test_the_desktop_refuses_an_application_nobody_put_on_the_list() -> None:
    computer = FakeComputer(surface=Surface.DESKTOP, focused="Mail")
    guard = GuardedComputer(computer, desktop())

    with pytest.raises(PermissionDeniedError, match="'Mail' is in front"):
        await guard.type("hello")


async def test_the_desktop_refuses_when_it_cannot_tell_what_is_in_front() -> None:
    """An unanswered question is not a reassuring answer."""
    computer = FakeComputer(surface=Surface.DESKTOP, focused=None)
    guard = GuardedComputer(computer, desktop())

    with pytest.raises(PermissionDeniedError, match="could not tell"):
        await guard.click(10, 10)


async def test_an_empty_allow_list_means_the_desktop_is_off_limits() -> None:
    computer = FakeComputer(surface=Surface.DESKTOP, focused="Preview")
    guard = GuardedComputer(computer, ComputerConstraints(applies_to_applications=True))

    with pytest.raises(PermissionDeniedError, match="may not act on the desktop"):
        await guard.click(10, 10)


async def test_the_browser_surface_is_not_asked_which_application_is_in_front() -> None:
    """A page has no application to choose between; asking would refuse everything."""
    computer = FakeComputer(surface=Surface.BROWSER, focused=None)
    guard = GuardedComputer(computer, BROWSER)

    await guard.click(10, 10)

    assert computer.names() == ["click"]


# --- The budget ---------------------------------------------------------------


async def test_the_action_budget_is_separate_from_the_run_s_step_limit() -> None:
    computer = FakeComputer()
    guard = GuardedComputer(
        computer, ComputerConstraints(max_actions=2, applies_to_applications=False)
    )

    await guard.click(1, 1)
    await guard.click(2, 2)
    with pytest.raises(PermissionDeniedError, match="all 2 of the actions"):
        await guard.click(3, 3)


async def test_looking_is_free_so_a_spent_run_can_still_say_what_it_sees() -> None:
    computer = FakeComputer()
    guard = GuardedComputer(
        computer, ComputerConstraints(max_actions=1, applies_to_applications=False)
    )

    await guard.click(1, 1)
    await guard.screenshot()

    assert guard.actions_left == 0
    assert computer.screenshots == 1


# --- The brake ----------------------------------------------------------------


async def test_the_stop_signal_is_read_before_anything_else_is_checked() -> None:
    """A user who pulled the brake is not asking for a better-aimed click."""
    computer = FakeComputer()
    guard = GuardedComputer(
        computer,
        ComputerConstraints(allowed_region=Region(0, 0, 10, 10),
                            applies_to_applications=False),
        stop_signal=EngagedStop("stop, wrong window"),
    )

    with pytest.raises(StopRequestedError, match="stop, wrong window"):
        await guard.click(9999, 9999)

    assert computer.actions == []


async def test_a_stop_halts_looking_too() -> None:
    guard = GuardedComputer(
        FakeComputer(), BROWSER, stop_signal=EngagedStop()
    )

    with pytest.raises(StopRequestedError):
        await guard.screenshot()


# --- The value type -----------------------------------------------------------


def test_a_region_reads_back_the_way_it_was_written() -> None:
    assert str(Region.parse("1280x800+10+20")) == "1280x800+10+20"
    assert Region.parse("800x600") == Region(0, 0, 800, 600)


def test_an_unusable_region_is_rejected_at_the_point_it_is_configured() -> None:
    with pytest.raises(ValueError, match="not a screen region"):
        Region.parse("the left half")
    with pytest.raises(ValueError, match="no area"):
        Region.parse("0x0+0+0")


def test_a_violation_names_the_action_it_refused() -> None:
    violation = ComputerConstraints(
        allowed_region=Region(0, 0, 10, 10)
    ).check_point(ComputerAction.CLICK, 50, 50)

    assert violation is not None
    assert violation.action is ComputerAction.CLICK
