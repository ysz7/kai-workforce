"""Turning a picture of a screen into coordinates something can act on.

This is the part of Computer Use that is actually hard. Driving a mouse is a few
lines of a library call; knowing *where* to put it is a model looking at pixels
and being right about them. So it is its own component, behind its own contract,
with its own model requirement - `VISION` - which the router answers from the
catalog like any other requirement.

Two decisions here.

**The vision call is separate from the employee's own model.** The employee
driving the task can be a text model with no eyes at all: it asks a question
about the screen, gets back a sentence and a coordinate, and carries on
reasoning in text. That keeps the loop readable, keeps the screenshot out of
the transcript that gets replayed on every subsequent step, and means a local
model too small to see can still operate a screen through one that can.

**The answer is parsed strictly and doubted by default.** A model that invents a
coordinate does not look any different from one that read it off the screen, so
targets that are outside the image are dropped rather than clamped: a click at
the clamped edge would be a click on something, and the wrong something.
"""

from __future__ import annotations

from typing import Any

import structlog

from application.employee_runtime.prompts import render
from domain.capabilities.models import Capability, CapabilityRequirement
from domain.computer.models import Screenshot, ScreenTarget, ScreenView
from domain.llm.json_output import extract_object
from domain.llm.models import (
    ImageContent,
    LLMRequest,
    Message,
    RoutingHints,
    TaskKind,
)
from domain.llm.protocols import LLM

log = structlog.get_logger(__name__)


class LLMScreenReader:
    """Implements `domain.computer.protocols.ScreenReader`."""

    def __init__(self, llm: LLM) -> None:
        self._llm = llm

    async def read(self, screenshot: Screenshot, question: str) -> ScreenView:
        return await self._ask(screenshot, "v1", question=question)

    async def confirm(self, screenshot: Screenshot, expectation: str) -> ScreenView:
        """Did the action do what it was supposed to do?

        Asked as its own call with its own prompt rather than as a variation of
        `read`, because the two want opposite dispositions: describing a screen
        should be generous, checking one should not.
        """
        view = await self._ask(screenshot, "confirm", expectation=expectation)
        # An unreadable answer to a yes/no question is a no. The alternative is
        # a run that treats "I could not tell" as "it worked".
        return view if view.confirmed is not None else _unconfirmed(view.answer)

    # --- Internals ------------------------------------------------------------

    async def _ask(self, screenshot: Screenshot, version: str, **values: str) -> ScreenView:
        prompt = render(
            "screen_reader",
            version,
            width=screenshot.width,
            height=screenshot.height,
            **values,
        )
        response = await self._llm.generate(
            LLMRequest(
                messages=(
                    Message.user(
                        prompt,
                        images=(
                            ImageContent(
                                data_url=screenshot.as_data_url(),
                                alt_text="a screenshot of the screen being operated",
                            ),
                        ),
                    ),
                ),
                temperature=0.0,
                response_format={"type": "json_object"},
            )
        )

        parsed = extract_object(response.content)
        if parsed is None:
            log.warning("screen.unreadable_answer", version=version)
            return _unconfirmed(
                "The screen could not be read: the vision model did not answer in a "
                "form the platform could use."
            )

        answer = str(parsed.get("answer", "")).strip()
        view = ScreenView(
            answer=answer or "The vision model returned no description.",
            targets=_targets(parsed.get("targets"), screenshot),
            confirmed=_confirmed(parsed.get("confirmed")),
        )
        log.info(
            "screen.read",
            targets=len(view.targets),
            confirmed=view.confirmed,
            width=screenshot.width,
            height=screenshot.height,
        )
        return view

    @staticmethod
    def routing() -> tuple[TaskKind, CapabilityRequirement, RoutingHints]:
        """Reading a screen needs eyes, and the router is told exactly that.

        Nothing here names a model. If no entry in the catalog offers `VISION`,
        this fails at routing with a message about the catalog - which is the
        right place for that to be fixed.
        """
        return (
            TaskKind.EXTRACTION,
            CapabilityRequirement(
                required=frozenset({Capability.VISION, Capability.TEXT_REASONING})
            ),
            RoutingHints(quality=0.8, cost_sensitivity=0.4),
        )


def _confirmed(raw: Any) -> bool | None:
    if raw is None:
        return None
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"true", "yes"}


def _targets(raw: Any, screenshot: Screenshot) -> tuple[ScreenTarget, ...]:
    if not isinstance(raw, list):
        return ()
    found: list[ScreenTarget] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            x, y = int(item["x"]), int(item["y"])
        except (KeyError, TypeError, ValueError):
            continue
        if not screenshot.bounds.contains(x, y):
            # Not clamped to the edge: a corrected coordinate still points at
            # something, and at something nobody chose.
            log.info("screen.target_out_of_frame", label=item.get("label"), x=x, y=y)
            continue
        found.append(
            ScreenTarget(
                label=str(item.get("label", "")).strip() or "unnamed",
                x=x,
                y=y,
                confidence=_confidence(item.get("confidence")),
            )
        )
    return tuple(found)


def _confidence(raw: Any) -> float:
    try:
        return min(max(float(raw), 0.0), 1.0)
    except (TypeError, ValueError):
        return 0.0


def _unconfirmed(answer: str) -> ScreenView:
    return ScreenView(answer=answer, confirmed=False)
