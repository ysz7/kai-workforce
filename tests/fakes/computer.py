"""A screen that is never touched and a reader that never looks.

The point of `FakeComputer` is the plan's own wording: actions are *recorded*,
not performed. The suite exercises the whole computer-use path - constraints,
the stop signal, verification after an action, the approval gate on the desktop
surface - on a machine where nothing moves and no window is in front.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass

from domain.computer.models import Screenshot, ScreenTarget, ScreenView, Surface
from domain.errors import ComputerUseError


def png_bytes(width: int = 8, height: int = 8) -> bytes:
    """A real, decodable PNG of one flat colour.

    Built rather than checked in as a fixture: an adapter that base64-encodes an
    image should be tested against bytes that actually are one, and a file
    nobody can read is a fixture nobody maintains.
    """
    raw = b"".join(b"\x00" + b"\x7f\x7f\x7f" * width for _ in range(height))

    def chunk(kind: bytes, payload: bytes) -> bytes:
        body = kind + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


@dataclass(frozen=True, slots=True)
class RecordedAction:
    name: str
    arguments: dict[str, object]


class FakeComputer:
    """Implements `domain.computer.protocols.Computer`. Records, never acts."""

    def __init__(
        self,
        *,
        surface: Surface = Surface.BROWSER,
        width: int = 1280,
        height: int = 800,
        focused: str | None = None,
        fails: str | None = None,
    ) -> None:
        self._surface = surface
        self.width = width
        self.height = height
        self.focused = focused
        #: The name of an action that should raise, for the failure paths.
        self.fails = fails
        self.actions: list[RecordedAction] = []
        self.screenshots = 0

    @property
    def surface(self) -> Surface:
        return self._surface

    def focused_application(self) -> str | None:
        return self.focused

    def names(self) -> list[str]:
        return [action.name for action in self.actions]

    def _record(self, name: str, **arguments: object) -> None:
        if self.fails == name:
            raise ComputerUseError(f"{name} failed on the fake surface")
        self.actions.append(RecordedAction(name, arguments))

    async def screenshot(self) -> Screenshot:
        self.screenshots += 1
        self._record("screenshot")
        return Screenshot(
            image=png_bytes(), width=self.width, height=self.height
        )

    async def click(self, x: int, y: int, *, clicks: int = 1) -> None:
        self._record("click", x=x, y=y, clicks=clicks)

    async def type(self, text: str) -> None:
        self._record("type", text=text)

    async def press(self, key: str) -> None:
        self._record("press", key=key)

    async def scroll(self, amount: int) -> None:
        self._record("scroll", amount=amount)


class FakeScreenReader:
    """Implements `domain.computer.protocols.ScreenReader` from canned answers."""

    def __init__(
        self,
        *,
        answer: str = "A page with a Search field in the middle.",
        targets: tuple[ScreenTarget, ...] = (ScreenTarget("Search field", 640, 400, 0.9),),
        confirms: bool = True,
    ) -> None:
        self.answer = answer
        self.targets = targets
        self.confirms = confirms
        self.questions: list[str] = []
        self.expectations: list[str] = []

    async def read(self, screenshot: Screenshot, question: str) -> ScreenView:
        self.questions.append(question)
        return ScreenView(answer=self.answer, targets=self.targets)

    async def confirm(self, screenshot: Screenshot, expectation: str) -> ScreenView:
        self.expectations.append(expectation)
        return ScreenView(answer=self.answer, confirmed=self.confirms)


class EngagedStop:
    """Implements `domain.computer.protocols.StopSignal`. Always on."""

    def __init__(self, reason: str = "stop, wrong window") -> None:
        self._reason = reason

    def engaged(self) -> bool:
        return True

    @property
    def reason(self) -> str:
        return self._reason
