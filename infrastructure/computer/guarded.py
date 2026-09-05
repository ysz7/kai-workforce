"""The bounds, applied in one place in front of any surface.

Same argument as the approval gate: a check written into each `Computer` would
be written slightly differently in each, and the implementation that forgot it
would be the one that could reach anything. So the confinement is a decorator
that is itself a `Computer` - the tools cannot tell they are talking to it, and
there is no path around it, because nothing else is ever handed out.

Order matters and is not arbitrary. The stop signal is read first, before the
budget and before the coordinates, because a user who pulled the brake is not
asking for a better-aimed click. Then the action budget, then where the click
would land, then what is in front of it - cheapest refusal first, and the
expensive question (asking the OS which application has focus) only for an
action that has survived everything else.
"""

from __future__ import annotations

from dataclasses import replace

from domain.computer.constraints import ComputerConstraints, ConstraintViolation
from domain.computer.models import ComputerAction, Screenshot, Surface
from domain.computer.protocols import Computer, StopSignal
from domain.errors import PermissionDeniedError, StopRequestedError
from infrastructure.observability.logging import get_logger

log = get_logger(__name__)


class GuardedComputer:
    """Implements `domain.computer.protocols.Computer` and confines one."""

    def __init__(
        self,
        computer: Computer,
        constraints: ComputerConstraints,
        *,
        stop_signal: StopSignal | None = None,
    ) -> None:
        self._computer = computer
        self._constraints = constraints
        self._stop = stop_signal
        self._actions = 0
        #: Set once a screenshot has told us how big the surface really is.
        self._clipped = False

    @property
    def surface(self) -> Surface:
        return self._computer.surface

    @property
    def constraints(self) -> ComputerConstraints:
        return self._constraints

    @property
    def actions_taken(self) -> int:
        return self._actions

    @property
    def actions_left(self) -> int:
        return max(self._constraints.max_actions - self._actions, 0)

    # --- Computer -------------------------------------------------------------

    async def screenshot(self) -> Screenshot:
        """Looking is free.

        It costs nothing outside the process and changes nothing, so it is not
        spent against the action budget - only the stop signal applies. An agent
        that has run out of actions can still be asked what it can see, which is
        what a useful final answer is made of.
        """
        self._check_stop(ComputerAction.SCREENSHOT)
        shot = await self._computer.screenshot()
        if not self._clipped:
            # The configured region is what the user asked for; the screen is
            # what exists. Clip once, from the first real screenshot, so a
            # region set for a bigger display does not refuse every click.
            self._constraints = self._constraints.within_the_screen(shot.bounds)
            self._clipped = True
            log.debug(
                "computer.region_clipped", region=str(self._constraints.allowed_region)
            )
        return shot

    async def click(self, x: int, y: int, *, clicks: int = 1) -> None:
        self._allow(ComputerAction.CLICK, point=(x, y))
        await self._computer.click(x, y, clicks=clicks)

    async def type(self, text: str) -> None:
        self._allow(ComputerAction.TYPE)
        await self._computer.type(text)

    async def press(self, key: str) -> None:
        self._allow(ComputerAction.PRESS)
        await self._computer.press(key)

    async def scroll(self, amount: int) -> None:
        self._allow(ComputerAction.SCROLL)
        await self._computer.scroll(amount)

    # --- The bounds -----------------------------------------------------------

    def _allow(
        self, action: ComputerAction, *, point: tuple[int, int] | None = None
    ) -> None:
        self._check_stop(action)

        if self._actions >= self._constraints.max_actions:
            raise PermissionDeniedError(
                f"This employee has used all {self._constraints.max_actions} of the "
                "actions it may take on a screen in one run."
            )

        if point is not None:
            self._refuse(self._constraints.check_point(action, *point))
        self._refuse(
            self._constraints.check_application(action, self._focused_application())
        )
        self._actions += 1

    def _check_stop(self, action: ComputerAction) -> None:
        if self._stop is not None and self._stop.engaged():
            log.warning("computer.stopped", action=action.value, reason=self._stop.reason)
            raise StopRequestedError(
                f"Stopped by the user before {action.value.lower()}: {self._stop.reason}"
            )

    def _focused_application(self) -> str | None:
        """Ask the surface what is in front, if it is the kind that knows."""
        query = getattr(self._computer, "focused_application", None)
        return query() if callable(query) else None

    @staticmethod
    def _refuse(violation: ConstraintViolation | None) -> None:
        if violation is None:
            return
        log.info(
            "computer.refused", action=violation.action.value, reason=violation.reason
        )
        raise PermissionDeniedError(violation.reason)

    def with_constraints(self, constraints: ComputerConstraints) -> GuardedComputer:
        """A second guard over the same surface, for an employee with other bounds."""
        return GuardedComputer(self._computer, replace(constraints), stop_signal=self._stop)
