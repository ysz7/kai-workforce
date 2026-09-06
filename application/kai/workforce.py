"""How KAI describes the people it can call on.

One function, used by three prompts, for a reason worth stating: the *only*
thing KAI knows about its workforce is what the registry hands it. There is no
list of employees in this package, no name in a prompt, and no branch on one.
Add a declaration under `employees/` and it appears here on the next run; delete
one and it stops being offered, with no edit anywhere in `application/kai/`.

What goes into the card is what a manager would need to choose: the role, what
the person is for, and - decisively - the tools they are allowed to use, because
that is the whole of what they can actually reach. Someone with no web tools
cannot look anything up, however well their role reads against the task.
"""

from __future__ import annotations

from domain.employees.definition import EmployeeDefinition


def describe(definitions: list[EmployeeDefinition]) -> str:
    """The workforce as a model should see it. Empty is said, not implied."""
    if not definitions:
        return "Nobody is declared. You have no one to give work to."
    return "\n\n".join(_card(definition) for definition in definitions)


def _card(definition: EmployeeDefinition) -> str:
    lines = [f"## {definition.name}", f"Role: {definition.role.title}"]
    if definition.role.description:
        lines.append(definition.role.description.strip())
    lines.append(f"Tools they may use: {', '.join(sorted(definition.allowed_tools)) or 'none'}")
    if definition.goals:
        lines.append(
            "They always try to: "
            + "; ".join(goal.text for goal in sorted(definition.goals, key=lambda g: g.priority))
        )
    lines.append(
        f"Limits per task: {definition.limits.max_steps} steps, "
        f"${definition.limits.max_cost_usd:g}"
    )
    return "\n".join(lines)
