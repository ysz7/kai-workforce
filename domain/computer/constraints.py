"""Where the hands are allowed to reach.

A `Computer` can touch anything its surface can touch, which on a desktop is
everything the user can. The confinement is the same idea as `Workspace` for
files: state the bounds once, resolve every action against them, and refuse
what falls outside instead of asking about it. A confirmation prompt for an
action that should never have been possible teaches the user to click through
prompts.

Three bounds, and each answers a different question:

- **which applications** - what may be in front when a key or a click lands;
- **which part of the screen** - a click outside the region is refused, so a
  misread coordinate cannot reach the menu bar;
- **how many actions** - a budget separate from the run's step limit, because
  one step of the loop can ask for several actions.

The default is the safe one on a desktop and the useless one everywhere else:
an empty application list means nothing is allowed. A surface that has no notion
of applications passes `applies_to_applications=False` and is judged on the other
two, which is what makes the browser path usable without the user enumerating
anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from domain.computer.models import ComputerAction, Region


@dataclass(frozen=True, slots=True)
class ConstraintViolation:
    """Why an action was refused, in the words the model is shown."""

    action: ComputerAction
    reason: str


@dataclass(frozen=True, slots=True)
class ComputerConstraints:
    """The bounds one employee's computer use runs inside."""

    allowed_applications: frozenset[str] = field(default_factory=frozenset)
    allowed_region: Region | None = None
    max_actions: int = 200
    #: False for a surface where "which application is in front" is not a
    #: question that can be asked, such as a page in a browser the platform owns.
    applies_to_applications: bool = True

    def within_the_screen(self, region: Region) -> ComputerConstraints:
        """Clip the allowed region to a surface that turned out to be smaller.

        A region configured for a 4K display and used on a laptop would otherwise
        refuse every click on the visible part of the screen.
        """
        if self.allowed_region is None:
            return replace(self, allowed_region=region)
        current = self.allowed_region
        x = max(current.x, region.x)
        y = max(current.y, region.y)
        right = min(current.x + current.width, region.x + region.width)
        bottom = min(current.y + current.height, region.y + region.height)
        return replace(
            self,
            allowed_region=Region(x, y, max(right - x, 0), max(bottom - y, 0)),
        )

    def check_point(self, action: ComputerAction, x: int, y: int) -> ConstraintViolation | None:
        if self.allowed_region is not None and not self.allowed_region.contains(x, y):
            return ConstraintViolation(
                action,
                f"({x}, {y}) is outside the part of the screen this employee may "
                f"use ({self.allowed_region}).",
            )
        return None

    def check_application(
        self, action: ComputerAction, name: str | None
    ) -> ConstraintViolation | None:
        """Refuse unless the thing in front is one the user named.

        `None` means the surface could not say what is in front. That is refused
        too: an unanswered question about where a keystroke is about to land is
        not the same as a reassuring answer.
        """
        if not self.applies_to_applications:
            return None
        if not self.allowed_applications:
            return ConstraintViolation(
                action,
                "No application is on this employee's allow-list, so it may not "
                "act on the desktop at all.",
            )
        if name is None:
            return ConstraintViolation(
                action, "The platform could not tell which application is in front."
            )
        if not any(allowed.lower() in name.lower() for allowed in self.allowed_applications):
            return ConstraintViolation(
                action,
                f"'{name}' is in front, and this employee may only act in "
                f"{', '.join(sorted(self.allowed_applications))}.",
            )
        return None
