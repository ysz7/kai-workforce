"""The contracts of the last resort interface.

Three of them, kept apart because they are implemented by different things and
faked separately in the suite: something that drives a surface, something that
reads one, and something the user can pull to make both stop.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from domain.computer.models import Screenshot, ScreenView, Surface


class Computer(Protocol):
    """The last interface an employee reaches for, and the one that makes the
    platform actually work on a machine rather than talk about it.

    Coordinates are the surface's own, with the origin at its top left, which is
    also the frame a `Screenshot` is in. No implementation is allowed to scale
    them silently: a model that clicked 40 pixels off should see that on the next
    screenshot rather than have it corrected out of view.
    """

    @property
    def surface(self) -> Surface: ...

    async def screenshot(self) -> Screenshot: ...

    async def click(self, x: int, y: int, *, clicks: int = 1) -> None: ...

    async def type(self, text: str) -> None: ...

    async def press(self, key: str) -> None: ...

    async def scroll(self, amount: int) -> None: ...


class ScreenReader(Protocol):
    """Turning a picture of a screen into something to act on.

    Separate from `Computer` on purpose: what can drive a surface and what can
    understand one are different capabilities, met by different components, and
    a desktop with no vision model configured should fail at understanding
    rather than at clicking.
    """

    async def read(self, screenshot: Screenshot, question: str) -> ScreenView: ...

    async def confirm(self, screenshot: Screenshot, expectation: str) -> ScreenView: ...


@runtime_checkable
class StopSignal(Protocol):
    """The user's hand on the brake.

    Limits stop a run that is spending too much; this stops one that is doing
    the wrong thing, at a moment nobody predicted, from outside the process.
    Checked before every action rather than between steps, because the action is
    what reaches the world.
    """

    def engaged(self) -> bool: ...

    @property
    def reason(self) -> str: ...
