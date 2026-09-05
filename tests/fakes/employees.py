"""Employee declarations built inline, so a test does not need a YAML file."""

from __future__ import annotations

from domain.capabilities.models import Capability
from domain.employees.definition import EmployeeDefinition, Goal, Role
from domain.employees.limits import ExecutionLimits
from domain.llm.models import ModelProfile


def definition(
    name: str = "researcher",
    *,
    tools: frozenset[str] = frozenset(),
    limits: ExecutionLimits | None = None,
    system_prompt: str = "You are a test employee.",
) -> EmployeeDefinition:
    return EmployeeDefinition.create(
        name,
        Role("Research Specialist", "Finds out what is true and says where it came from."),
        goals=(Goal("Answer the question that was asked."),),
        allowed_tools=tools,
        model_profile=ModelProfile(capabilities=frozenset({Capability.TEXT_REASONING})),
        limits=limits or ExecutionLimits(),
        system_prompt=system_prompt,
    )
