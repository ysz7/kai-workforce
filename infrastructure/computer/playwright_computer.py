"""Computer Use inside a page the platform already owns.

This is the rung of the hierarchy immediately below the DOM, and it exists
because plenty of a real page is not addressable by structure: a canvas, a PDF
viewer, an embedded widget, a map. The employee has already opened the page with
`browser.open`; this drives the same tab rather than a second engine, so what
the model is shown and what the click lands on cannot drift apart.

It is deliberately the *first* computer surface. Everything about acting on
pixels - coordinates from a vision model, verification by screenshot, the
constraint guard - is exercised here, where the blast radius is one tab, before
any of it is pointed at the user's own desktop.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from domain.computer.models import Screenshot, Surface
from domain.errors import ComputerUseError
from infrastructure.observability.logging import get_logger

log = get_logger(__name__)

#: What a page is assumed to be when Playwright will not say. Chromium's own
#: default; used only so a screenshot still reports usable bounds.
FALLBACK_VIEWPORT = (1280, 720)


class PageProvider(Protocol):
    """Anything that can hand over the live page. `PlaywrightBrowser` is one."""

    async def page(self) -> Any: ...


class PlaywrightComputer:
    """Implements `domain.computer.protocols.Computer` over an open page."""

    def __init__(self, pages: PageProvider | Callable[[], Awaitable[Any]]) -> None:
        supplier = getattr(pages, "page", None)
        self._pages: Callable[[], Awaitable[Any]] = supplier if callable(supplier) else pages

    @property
    def surface(self) -> Surface:
        return Surface.BROWSER

    async def screenshot(self) -> Screenshot:
        page = await self._page()
        image = await self._guard("screenshot", page.screenshot(type="png"))
        width, height = self._viewport(page)
        return Screenshot(image=image, width=width, height=height)

    async def click(self, x: int, y: int, *, clicks: int = 1) -> None:
        page = await self._page()
        await self._guard("click", page.mouse.click(x, y, click_count=max(clicks, 1)))
        log.info("computer.clicked", surface="BROWSER", x=x, y=y, clicks=clicks)

    async def type(self, text: str) -> None:
        page = await self._page()
        # Typed rather than set: a page that only reacts to keystrokes - most
        # autocomplete fields - sees nothing at all from a value assignment.
        await self._guard("type", page.keyboard.type(text))
        log.info("computer.typed", surface="BROWSER", characters=len(text))

    async def press(self, key: str) -> None:
        page = await self._page()
        await self._guard("press", page.keyboard.press(key))
        log.info("computer.pressed", surface="BROWSER", key=key)

    async def scroll(self, amount: int) -> None:
        page = await self._page()
        await self._guard("scroll", page.mouse.wheel(0, amount))
        log.info("computer.scrolled", surface="BROWSER", amount=amount)

    # --- Internals ------------------------------------------------------------

    async def _page(self) -> Any:
        return await self._pages()

    @staticmethod
    def _viewport(page: Any) -> tuple[int, int]:
        viewport = getattr(page, "viewport_size", None)
        if isinstance(viewport, dict) and viewport.get("width") and viewport.get("height"):
            return int(viewport["width"]), int(viewport["height"])
        return FALLBACK_VIEWPORT

    @staticmethod
    async def _guard(action: str, awaitable: Any) -> Any:
        """Playwright raises its own exception types; the domain has one for this."""
        try:
            return await awaitable
        except Exception as error:
            raise ComputerUseError(f"{action} failed on the page: {error}") from error
