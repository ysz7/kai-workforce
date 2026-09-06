"""Checking a declaration against the machine it will run on.

An employee is a file, and a file can say things that are not true: a tool name
with a typo in it, a capability nothing backs, a job nobody can do. None of
those fail loudly at runtime. The tool is simply never offered to the model, the
capability search never finds the employee, and the run produces a worse answer
for a reason nobody can see in the trace. That is the failure mode this exists
against - a declaration that is wrong and *quiet*.

Two rules decide what is an error and what is a warning, and the difference is
not severity but **who can fix it**:

* an **error** is a contradiction inside the declaration - it claims a
  capability that nothing it holds could provide, *and* everything it holds is
  present to check. No machine, no configuration and no model makes that true.
* a **warning** is a mismatch with *this* machine - a tool that exists in the
  codebase but is switched off here, or a capability declared by a tool the
  employee holds but not by the employee itself. The declaration may be right
  and the machine merely differently configured.

The second clause of the error rule is the one that took a test to find. An
employee holding a tool this machine does not offer cannot be convicted of
claiming too much: the missing tool may be exactly what backed the claim. That
case is already reported - as the missing tool - and reporting it twice, once as
a fault of the declaration, would be wrong the first time.

Kept in `domain/` and given the tools as data, so it can be run anywhere the two
are known - the container at start-up, `kai employees`, a test - without any of
them needing to agree on where a tool comes from.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum

from domain.capabilities.models import Capability
from domain.employees.definition import EmployeeDefinition

#: What a tool lets an employee do, by tool name. Exactly what a `ToolRegistry`
#: can produce from its specs, expressed as data so this module needs no
#: registry, no adapter and no import out of the domain.
ToolCapabilities = Mapping[str, frozenset[Capability]]


class Severity(StrEnum):
    #: Wrong wherever it runs. The declaration contradicts itself.
    ERROR = "ERROR"
    #: Wrong here. The machine may simply be configured differently.
    WARNING = "WARNING"


@dataclass(frozen=True, slots=True)
class Issue:
    employee: str
    message: str
    severity: Severity = Severity.ERROR

    @property
    def is_error(self) -> bool:
        return self.severity is Severity.ERROR

    def __str__(self) -> str:
        return f"{self.severity.value}: {self.employee}: {self.message}"


def check(definition: EmployeeDefinition, offered: ToolCapabilities) -> tuple[Issue, ...]:
    """Everything wrong with one declaration, worst first."""
    issues = [
        *_missing_tools(definition, offered),
        *_unbacked_capabilities(definition, offered),
        *_undeclared_capabilities(definition, offered),
        *_can_do_nothing(definition),
    ]
    return tuple(sorted(issues, key=lambda issue: (not issue.is_error, issue.message)))


def check_all(
    definitions: Iterable[EmployeeDefinition], offered: ToolCapabilities
) -> tuple[Issue, ...]:
    return tuple(issue for d in definitions for issue in check(d, offered))


def errors(issues: Iterable[Issue]) -> tuple[Issue, ...]:
    return tuple(issue for issue in issues if issue.is_error)


# --- The rules ----------------------------------------------------------------


def _missing_tools(
    definition: EmployeeDefinition, offered: ToolCapabilities
) -> list[Issue]:
    """A tool it lists that this machine does not have.

    A warning, not an error, and the wording matters: the browser tools are an
    extra and the desktop ones are behind a flag, so "not offered here" is a
    normal state of affairs and "does not exist" would be a lie half the time.
    The employee still loses the tool - silently, at runtime - which is why it
    is said at all.
    """
    absent = sorted(definition.allowed_tools - set(offered))
    if not absent:
        return []
    known = ", ".join(sorted(offered)) or "none"
    return [
        Issue(
            employee=definition.name,
            message=(
                f"lists {', '.join(absent)}, which this machine does not offer. "
                f"It will not be available to this employee. Offered here: {known}."
            ),
            severity=Severity.WARNING,
        )
    ]


def _unbacked_capabilities(
    definition: EmployeeDefinition, offered: ToolCapabilities
) -> list[Issue]:
    """A capability it claims that nothing it holds could provide.

    An error, because it is false on every machine: KAI searches by these, so an
    employee claiming CODE with no tool that runs any will be handed work it
    cannot begin.

    Only where the whole declaration can be checked, though. An employee holding
    a tool this machine does not offer might be backed by exactly that tool, and
    the missing tool is already reported on its own; convicting the declaration
    as well would be wrong.

    Capabilities the *model* provides - reasoning, long context, vision - are
    backed by the model profile rather than by a tool, and are not faulted here.
    """
    if definition.allowed_tools - set(offered):
        return []
    backed = _from_tools(definition, offered) | definition.model_profile.capabilities
    unbacked = sorted(str(c) for c in definition.capabilities - backed)
    if not unbacked:
        return []
    return [
        Issue(
            employee=definition.name,
            message=(
                f"claims {', '.join(unbacked)}, but nothing it may use provides it. "
                "Grant a tool that does, or stop claiming it."
            ),
        )
    ]


def _undeclared_capabilities(
    definition: EmployeeDefinition, offered: ToolCapabilities
) -> list[Issue]:
    """A capability its tools give it that it does not claim.

    The quiet one. The employee can do the work and KAI will never send it any,
    because discovery reads the declaration and not the tool list. Left as a
    warning because keeping a capability out of the declaration is a legitimate
    thing to want - a tool held for one narrow purpose need not advertise the
    whole category.
    """
    if not definition.capabilities:
        # It declared none at all, which `_can_do_nothing` covers on its own
        # terms. Listing every capability of every tool here would bury that.
        return []
    missing = sorted(str(c) for c in _from_tools(definition, offered) - definition.capabilities)
    if not missing:
        return []
    return [
        Issue(
            employee=definition.name,
            message=(
                f"may use tools that provide {', '.join(missing)} but does not declare it, "
                "so it will not be found by a search for that work."
            ),
            severity=Severity.WARNING,
        )
    ]


def _from_tools(
    definition: EmployeeDefinition, offered: ToolCapabilities
) -> frozenset[Capability]:
    """What the tools this employee may use, and this machine has, provide."""
    return frozenset().union(
        frozenset(), *(offered.get(tool, frozenset()) for tool in definition.allowed_tools)
    )


def _can_do_nothing(definition: EmployeeDefinition) -> list[Issue]:
    if definition.allowed_tools or definition.capabilities:
        return []
    return [
        Issue(
            employee=definition.name,
            message=(
                "has no tools and declares no capabilities, so it can only think "
                "and answer. That is a valid employee; say so deliberately."
            ),
            severity=Severity.WARNING,
        )
    ]
