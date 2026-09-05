from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class WorkflowTrigger(StrEnum):
    MANUAL = "MANUAL"
    SCHEDULED = "SCHEDULED"
    EVENT = "EVENT"
    CONDITIONAL = "CONDITIONAL"


@dataclass(frozen=True, slots=True)
class WorkflowStep:
    name: str
    employee: str
    instruction: str
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WorkflowDefinition:
    """A predefined process. Adding one must not require changing any employee."""

    name: str
    description: str = ""
    trigger: WorkflowTrigger = WorkflowTrigger.MANUAL
    steps: tuple[WorkflowStep, ...] = ()
    inputs: dict[str, Any] = field(default_factory=dict)
