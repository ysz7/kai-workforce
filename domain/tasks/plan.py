"""The plan for one task: the steps an employee intends to take.

Not to be confused with `domain.workforce.protocols.Plan`, which is KAI's
decomposition of an objective into *tasks*. This one lives inside a single task
and belongs to the employee executing it.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any


@dataclass(frozen=True, slots=True)
class PlanStep:
    index: int
    description: str
    #: What the employee expects to be true once this step is done. The verifier
    #: has something concrete to check against, instead of a vibe.
    expected_outcome: str = ""
    done: bool = False

    def complete(self) -> PlanStep:
        return replace(self, done=True)


@dataclass(frozen=True, slots=True)
class TaskPlan:
    steps: tuple[PlanStep, ...] = ()
    rationale: str = ""

    @classmethod
    def of(cls, *descriptions: str, rationale: str = "") -> TaskPlan:
        return cls(
            steps=tuple(
                PlanStep(index=i, description=text) for i, text in enumerate(descriptions)
            ),
            rationale=rationale,
        )

    @property
    def is_empty(self) -> bool:
        return not self.steps

    @property
    def next_step(self) -> PlanStep | None:
        return next((step for step in self.steps if not step.done), None)

    def complete_through(self, index: int) -> TaskPlan:
        """Mark every step up to and including `index` as done.

        A model that reports finishing step 3 has, in practice, finished 1 and 2
        as well; tracking them individually invites a plan that never completes.
        """
        return replace(
            self,
            steps=tuple(step.complete() if step.index <= index else step for step in self.steps),
        )

    # --- Persistence ----------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "rationale": self.rationale,
            "steps": [
                {
                    "index": step.index,
                    "description": step.description,
                    "expected_outcome": step.expected_outcome,
                    "done": step.done,
                }
                for step in self.steps
            ],
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> TaskPlan | None:
        if not raw:
            return None
        return cls(
            steps=tuple(
                PlanStep(
                    index=int(step.get("index", i)),
                    description=step.get("description", ""),
                    expected_outcome=step.get("expected_outcome", ""),
                    done=bool(step.get("done", False)),
                )
                for i, step in enumerate(raw.get("steps", ()))
            ),
            rationale=raw.get("rationale", ""),
        )


@dataclass(frozen=True, slots=True)
class Observation:
    """What the employee made of a step before deciding the next one.

    Kept explicit on purpose. A loop that goes straight from a tool result to the
    next tool call has no place to notice that the result was empty, wrong, or
    already answered the question.
    """

    step: int
    summary: str
    succeeded: bool = True
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "summary": self.summary,
            "succeeded": self.succeeded,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Observation:
        return cls(
            step=int(raw.get("step", 0)),
            summary=raw.get("summary", ""),
            succeeded=bool(raw.get("succeeded", True)),
            details=raw.get("details", {}),
        )
