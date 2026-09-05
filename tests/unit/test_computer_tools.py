"""The look-act-check loop, and the rule that decides who has to approve it."""

from __future__ import annotations

from application.employee_runtime.approvals import ApprovalGate
from domain.approvals.gate import assess_call
from domain.computer.interfaces import InterfaceLevel
from domain.computer.models import ScreenTarget, Surface
from domain.policies.models import Decision, RiskLevel
from domain.tasks.task import Task
from infrastructure.tools.computer import computer_tools
from tests.fakes.approvals import ScriptedApprovalService
from tests.fakes.computer import FakeComputer, FakeScreenReader
from tests.fakes.employees import definition


def tools(surface: Surface = Surface.BROWSER, **kwargs: object):
    computer = FakeComputer(surface=surface, **kwargs)  # type: ignore[arg-type]
    reader = FakeScreenReader()
    return computer, reader, {t.spec.name: t for t in computer_tools(computer, reader)}


# --- Looking ------------------------------------------------------------------


async def test_the_screen_tool_answers_with_coordinates_not_with_prose() -> None:
    """Without a coordinate, "the button is in the toolbar" is not actionable."""
    _, _, by_name = tools()

    result = await by_name["computer.screen"].execute({"question": "where is search?"})

    assert result.success
    assert result.output["targets"] == [
        {"label": "Search field", "x": 640, "y": 400, "confidence": 0.9}
    ]
    assert result.output["screen_width"] == 1280


async def test_verifying_touches_nothing() -> None:
    computer, reader, by_name = tools()

    result = await by_name["computer.verify"].execute({"expectation": "the dialog is open"})

    assert result.output["verified"] is True
    assert computer.names() == ["screenshot"]
    assert reader.expectations == ["the dialog is open"]


# --- Acting, then checking ----------------------------------------------------


async def test_an_action_with_an_expectation_is_confirmed_by_looking() -> None:
    computer, reader, by_name = tools()

    result = await by_name["computer.click"].execute(
        {"x": 640, "y": 400, "expect": "the search field has focus"}
    )

    assert result.output["verified"] is True
    assert computer.names() == ["click", "screenshot"]
    assert reader.expectations == ["the search field has focus"]


async def test_a_screen_that_does_not_show_the_expected_thing_is_reported_as_such() -> None:
    """The result of the check, not the fact that the click was issued."""
    computer = FakeComputer()
    reader = FakeScreenReader(answer="Still the login page.", confirms=False)
    by_name = {t.spec.name: t for t in computer_tools(computer, reader)}

    result = await by_name["computer.click"].execute(
        {"x": 10, "y": 10, "expect": "the inbox is open"}
    )

    assert result.success
    assert result.output["verified"] is False
    assert result.output["screen_shows"] == "Still the login page."


async def test_an_action_without_an_expectation_says_it_checked_nothing() -> None:
    """Silence would read as success. It has to say it did not look."""
    computer, _, by_name = tools()

    result = await by_name["computer.press"].execute({"key": "Enter"})

    assert result.output["verified"] is False
    assert "nothing was checked" in result.output["note"]
    assert computer.names() == ["press"]


async def test_typed_text_is_never_echoed_back_into_the_transcript() -> None:
    """What gets typed into a screen is often a credential."""
    _, _, by_name = tools()

    result = await by_name["computer.type"].execute({"text": "hunter2"})

    assert "hunter2" not in str(result.output)
    assert result.output["typed_characters"] == 7


# --- The two surfaces ---------------------------------------------------------


def test_the_two_surfaces_get_different_names_so_they_can_be_granted_separately() -> None:
    _, _, browser = tools(Surface.BROWSER)
    _, _, desktop = tools(Surface.DESKTOP, focused="Preview")

    assert "computer.click" in browser and "desktop.click" not in browser
    assert "desktop.click" in desktop and "computer.click" not in desktop


def test_each_surface_declares_the_rung_of_the_hierarchy_it_is_on() -> None:
    _, _, browser = tools(Surface.BROWSER)
    _, _, desktop = tools(Surface.DESKTOP, focused="Preview")

    assert browser["computer.click"].spec.interface_level is InterfaceLevel.COMPUTER_USE
    assert desktop["desktop.click"].spec.interface_level is InterfaceLevel.DESKTOP


def test_a_tool_points_at_the_sibling_this_employee_actually_has() -> None:
    _, _, desktop = tools(Surface.DESKTOP, focused="Preview")

    assert "desktop.screen" in desktop["desktop.click"].spec.description
    assert "computer.screen" not in desktop["desktop.click"].spec.description


# --- Who has to say yes -------------------------------------------------------


def test_clicking_inside_a_page_the_platform_opened_does_not_need_a_person() -> None:
    _, _, by_name = tools(Surface.BROWSER)
    tool = by_name["computer.click"]

    decision = assess_call(tool.spec, tool.assess({"x": 1, "y": 1}))

    assert decision.decision is Decision.ALLOW
    assert decision.risk_level is RiskLevel.MEDIUM


def test_clicking_on_the_user_s_own_desktop_waits_for_a_person() -> None:
    """Same click, different surface, different act. See ADR 0005."""
    _, _, by_name = tools(Surface.DESKTOP, focused="Preview")
    tool = by_name["desktop.click"]

    decision = assess_call(tool.spec, tool.assess({"x": 1, "y": 1}))

    assert decision.decision is Decision.REQUIRE_APPROVAL
    assert "desktop" in decision.reason


def test_looking_at_the_desktop_is_not_an_irreversible_action() -> None:
    _, _, by_name = tools(Surface.DESKTOP, focused="Preview")

    assert by_name["desktop.screen"].spec.reversible
    assert assess_call(by_name["desktop.screen"].spec).decision is Decision.ALLOW


async def test_the_gate_sits_in_front_of_a_desktop_action_like_any_other() -> None:
    _, _, by_name = tools(Surface.DESKTOP, focused="Preview")
    service = ScriptedApprovalService.rejecting()
    gate = ApprovalGate(service)
    tool = by_name["desktop.click"]

    outcome = await gate.check(
        tool, {"x": 5, "y": 5}, Task.create("do the thing"), definition()
    )

    assert not outcome.allowed
    assert service.requests


# --- Failure ------------------------------------------------------------------


async def test_a_surface_that_fails_comes_back_as_a_result_the_model_can_read() -> None:
    computer = FakeComputer(fails="click")
    by_name = {t.spec.name: t for t in computer_tools(computer, FakeScreenReader())}

    result = await by_name["computer.click"].execute({"x": 1, "y": 1})

    assert not result.success
    assert "ComputerUseError" in (result.error or "")


def test_the_reader_is_not_built_until_a_tool_actually_runs() -> None:
    """Listing the registry must not route a model: `kai tools` does nothing else."""
    built = []

    def eyes() -> FakeScreenReader:
        built.append(1)
        return FakeScreenReader()

    made = computer_tools(FakeComputer(), eyes)
    _ = [tool.spec.name for tool in made]

    assert built == []
    assert made[0].eyes is not None
    assert built == [1]


def test_a_target_can_be_found_by_the_label_the_model_used() -> None:
    from domain.computer.models import ScreenView

    view = ScreenView("...", targets=(ScreenTarget("Save Button", 5, 6),))

    assert view.target("save button") == ScreenTarget("Save Button", 5, 6)
    assert view.target("cancel") is None
