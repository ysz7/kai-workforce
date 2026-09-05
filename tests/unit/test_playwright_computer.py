"""The page surface, over a page object that records instead of rendering.

Playwright itself is an optional extra and never runs in the suite. What is
worth checking here is the part that is this platform's decision rather than the
library's: that it drives the tab the employee already opened, that a screenshot
reports the frame its coordinates are in, and that a library exception becomes
an error the rest of the platform understands.
"""

from __future__ import annotations

import pytest

from domain.computer.models import Surface
from domain.errors import ComputerUseError
from infrastructure.computer.playwright_computer import (
    FALLBACK_VIEWPORT,
    PlaywrightComputer,
)
from tests.fakes.computer import png_bytes


class FakeMouse:
    def __init__(self, log: list) -> None:
        self._log = log

    async def click(self, x: int, y: int, click_count: int = 1) -> None:
        self._log.append(("click", x, y, click_count))

    async def wheel(self, dx: int, dy: int) -> None:
        self._log.append(("wheel", dx, dy))


class FakeKeyboard:
    def __init__(self, log: list) -> None:
        self._log = log

    async def type(self, text: str) -> None:
        self._log.append(("type", text))

    async def press(self, key: str) -> None:
        self._log.append(("press", key))


class FakePage:
    def __init__(self, viewport: dict | None = None, *, breaks: bool = False) -> None:
        self.log: list = []
        self.viewport_size = viewport
        self.mouse = FakeMouse(self.log)
        self.keyboard = FakeKeyboard(self.log)
        self._breaks = breaks

    async def screenshot(self, type: str = "png") -> bytes:
        if self._breaks:
            raise RuntimeError("the page went away")
        self.log.append(("screenshot", type))
        return png_bytes()


class OneTab:
    """Stands in for `PlaywrightBrowser`: hands out the page it already has."""

    def __init__(self, page: FakePage) -> None:
        self._page = page
        self.asked = 0

    async def page(self) -> FakePage:
        self.asked += 1
        return self._page


def computer(page: FakePage) -> tuple[OneTab, PlaywrightComputer]:
    tab = OneTab(page)
    return tab, PlaywrightComputer(tab)


def test_the_surface_says_what_it_is() -> None:
    _, driver = computer(FakePage())
    assert driver.surface is Surface.BROWSER


async def test_it_drives_the_tab_the_employee_already_opened() -> None:
    """Two engines side by side would show the model one page and click another."""
    tab, driver = computer(FakePage({"width": 800, "height": 600}))

    await driver.click(10, 20)
    await driver.type("hello")

    assert tab.asked == 2
    assert tab._page.log == [("click", 10, 20, 1), ("type", "hello")]


async def test_a_screenshot_reports_the_frame_its_coordinates_are_in() -> None:
    _, driver = computer(FakePage({"width": 1024, "height": 768}))

    shot = await driver.screenshot()

    assert (shot.width, shot.height) == (1024, 768)
    assert shot.image.startswith(b"\x89PNG")


async def test_a_page_that_will_not_say_its_size_still_gives_usable_bounds() -> None:
    _, driver = computer(FakePage(None))

    shot = await driver.screenshot()

    assert (shot.width, shot.height) == FALLBACK_VIEWPORT


async def test_a_double_click_is_two_and_not_two_calls() -> None:
    page = FakePage({"width": 800, "height": 600})
    _, driver = computer(page)

    await driver.click(1, 2, clicks=2)

    assert page.log == [("click", 1, 2, 2)]


async def test_scrolling_is_vertical_and_signed_the_same_way_as_everywhere_else() -> None:
    page = FakePage({"width": 800, "height": 600})
    _, driver = computer(page)

    await driver.scroll(250)

    assert page.log == [("wheel", 0, 250)]


async def test_a_library_failure_becomes_an_error_the_platform_understands() -> None:
    _, driver = computer(FakePage(breaks=True))

    with pytest.raises(ComputerUseError, match="screenshot failed on the page"):
        await driver.screenshot()


async def test_a_plain_callable_works_as_well_as_a_browser() -> None:
    page = FakePage({"width": 800, "height": 600})

    async def supply() -> FakePage:
        return page

    await PlaywrightComputer(supply).press("Enter")

    assert page.log == [("press", "Enter")]
