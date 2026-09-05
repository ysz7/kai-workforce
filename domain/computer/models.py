"""What a screen is, in the terms the platform needs to reason about one.

The plan sketched `screenshot() -> bytes`. Bytes alone are not enough: the whole
point of a screenshot here is that a model looks at it and answers with
coordinates, and coordinates are meaningless without the size of the surface
they refer to. So a screenshot carries its own dimensions and media type, and
the caller never has to decode the image to find out where it may click.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class Surface(StrEnum):
    """What a `Computer` is actually driving.

    It changes what an action means. A click in a page the employee opened is
    undone by going back; a click on the desktop can be anything at all, and the
    risk assessment of the computer tools reads this to tell the two apart.
    """

    BROWSER = "BROWSER"
    DESKTOP = "DESKTOP"


class ComputerAction(StrEnum):
    """The verbs a `Computer` offers, named so a constraint can refer to one."""

    SCREENSHOT = "SCREENSHOT"
    CLICK = "CLICK"
    TYPE = "TYPE"
    PRESS = "PRESS"
    SCROLL = "SCROLL"


@dataclass(frozen=True, slots=True)
class Region:
    """A rectangle of the surface, in the surface's own pixels."""

    x: int
    y: int
    width: int
    height: int

    def contains(self, x: int, y: int) -> bool:
        return self.x <= x < self.x + self.width and self.y <= y < self.y + self.height

    def __str__(self) -> str:
        return f"{self.width}x{self.height}+{self.x}+{self.y}"

    @classmethod
    def parse(cls, text: str) -> Region:
        """Read the X geometry form, `WIDTHxHEIGHT+X+Y`, offsets optional.

        Borrowed rather than invented: it is the notation a user who has ever
        placed a window already knows, and it round-trips with `__str__`.
        """
        cleaned = text.strip().lower().replace(" ", "")
        try:
            size, *offsets = cleaned.split("+")
            width, height = (int(part) for part in size.split("x"))
            x, y = (int(offsets[i]) if i < len(offsets) else 0 for i in (0, 1))
        except (ValueError, TypeError) as error:
            raise ValueError(
                f"'{text}' is not a screen region. Write it as WIDTHxHEIGHT+X+Y, "
                "for example 1280x800+0+0."
            ) from error
        if width <= 0 or height <= 0:
            raise ValueError(f"'{text}' is a screen region with no area")
        return cls(x=x, y=y, width=width, height=height)


@dataclass(frozen=True, slots=True)
class Screenshot:
    """One look at the surface."""

    image: bytes
    width: int
    height: int
    media_type: str = "image/png"
    taken_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def bounds(self) -> Region:
        return Region(0, 0, self.width, self.height)

    def as_data_url(self) -> str:
        """The form every provider that accepts an inline image understands.

        Encoded here rather than in each adapter: the encoding is a property of
        the image, and doing it per adapter is how two adapters end up disagreeing
        about which one owns the `data:` prefix.
        """
        return f"data:{self.media_type};base64,{base64.b64encode(self.image).decode('ascii')}"


@dataclass(frozen=True, slots=True)
class ScreenTarget:
    """Something on the screen a model says it can see, and where it is.

    This is the value the whole vision path exists to produce: without a
    coordinate, "the Save button is in the toolbar" is not something a computer
    can act on.
    """

    label: str
    x: int
    y: int
    confidence: float = 0.0


@dataclass(frozen=True, slots=True)
class ScreenView:
    """What a model saw when it was shown a screenshot and asked a question."""

    answer: str
    targets: tuple[ScreenTarget, ...] = ()
    #: Set only when the question was a yes/no check on the state of the screen.
    confirmed: bool | None = None

    def target(self, label: str) -> ScreenTarget | None:
        wanted = label.strip().lower()
        for candidate in self.targets:
            if candidate.label.strip().lower() == wanted:
                return candidate
        return None
