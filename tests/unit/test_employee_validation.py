"""A declaration that is wrong should say so, not go quiet.

Every failure here is one that costs nothing at runtime and everything to the
result: a tool that is never offered, a capability that is never searched, an
employee that will be handed work it cannot begin. None of them raises. That is
what makes them worth a check of their own.
"""

from __future__ import annotations

from domain.capabilities.models import Capability
from domain.employees.validation import Severity, check, check_all, errors
from tests.fakes.employees import definition

OFFERED = {
    "fs.read": frozenset({Capability.FILE_ACCESS}),
    "fs.write": frozenset({Capability.FILE_ACCESS}),
    "web.search": frozenset({Capability.WEB_BROWSING}),
    "code.run": frozenset({Capability.CODE}),
}


def employee(*, tools=frozenset(), capabilities=frozenset(), name="worker"):
    from dataclasses import replace

    return replace(definition(name, tools=tools), capabilities=capabilities)


# --- Nothing wrong ------------------------------------------------------------


def test_a_declaration_backed_by_its_tools_has_nothing_to_say() -> None:
    consistent = employee(
        tools=frozenset({"fs.read", "code.run"}),
        capabilities=frozenset({Capability.FILE_ACCESS, Capability.CODE}),
    )
    assert check(consistent, OFFERED) == ()


def test_the_shipped_workforce_is_consistent_with_the_tools_it_ships_with() -> None:
    """The declarations in this repository, against the tools in this repository.

    Not a style check: this is the one that fires when somebody adds an employee
    and gets a tool name slightly wrong.
    """
    from pathlib import Path

    from infrastructure.employees.yaml_registry import YamlEmployeeRegistry
    from infrastructure.tools.builtin import build_registry

    root = Path(__file__).resolve().parents[2]
    registry = build_registry(workspace_root=root / "employees")  # nothing is written
    from domain.policies.models import ActorKind, SimpleActor

    everything = SimpleActor("test", ActorKind.SYSTEM, frozenset({"*"}))
    offered = {spec.name: spec.capabilities for spec in registry.list_specs(everything)}
    # The screen tools need a live surface to build, so they are not in `offered`
    # here; an employee that lists them is warned about, which is correct on a
    # machine that has none, and is not what this test is about.
    declared = YamlEmployeeRegistry(root / "employees").list()

    assert declared, "the check is worthless if it finds no employees"
    assert errors(check_all(declared, offered)) == ()


# --- Claiming what it cannot do -----------------------------------------------


def test_claiming_a_capability_nothing_backs_is_an_error() -> None:
    """Wrong on every machine: KAI will hand it work it cannot begin."""
    liar = employee(tools=frozenset({"fs.read"}), capabilities=frozenset({Capability.CODE}))

    issues = check(liar, OFFERED)
    faults = errors(issues)

    assert len(faults) == 1
    assert "claims CODE" in faults[0].message
    assert faults[0] is issues[0], "an error is reported before any warning"


def test_a_capability_the_model_provides_is_backed_by_the_model() -> None:
    """Reasoning and vision come from the model, not from a tool."""
    from dataclasses import replace

    from domain.llm.models import ModelProfile

    thinker = replace(
        employee(capabilities=frozenset({Capability.TEXT_REASONING})),
        model_profile=ModelProfile(capabilities=frozenset({Capability.TEXT_REASONING})),
    )

    assert errors(check(thinker, OFFERED)) == ()


# --- Mismatches with this machine ---------------------------------------------


def test_a_claim_is_not_faulted_while_one_of_its_tools_is_missing() -> None:
    """The missing tool may be exactly what backed the claim.

    It is already reported as a missing tool. Convicting the declaration as well
    would be wrong the first time, not merely noisy.
    """
    unknowable = employee(
        tools=frozenset({"fs.read", "computer.screen"}),
        capabilities=frozenset({Capability.FILE_ACCESS, Capability.COMPUTER_USE}),
    )

    issues = check(unknowable, OFFERED)

    assert errors(issues) == ()
    assert any("computer.screen" in issue.message for issue in issues)


def test_a_tool_this_machine_does_not_offer_is_a_warning_not_an_error() -> None:
    """The browser is an extra and the desktop is behind a flag.

    "Does not exist" would be a lie half the time; "not offered here" is what is
    actually known, and it still costs the employee the tool.
    """
    optimist = employee(
        tools=frozenset({"fs.read", "browser.open"}),
        capabilities=frozenset({Capability.FILE_ACCESS}),
    )

    issues = check(optimist, OFFERED)

    assert [issue.severity for issue in issues] == [Severity.WARNING]
    assert "browser.open" in issues[0].message
    assert "does not offer" in issues[0].message
    assert errors(issues) == ()


def test_a_typo_in_a_tool_name_is_caught_as_the_same_thing() -> None:
    issues = check(
        employee(tools=frozenset({"fs.raed"}), capabilities=frozenset({Capability.FILE_ACCESS})),
        OFFERED,
    )
    assert any("fs.raed" in issue.message for issue in issues)


def test_a_capability_it_has_but_does_not_declare_is_a_warning() -> None:
    """The quiet one: it could do the work, and will never be sent any."""
    modest = employee(
        tools=frozenset({"fs.read", "code.run"}),
        capabilities=frozenset({Capability.FILE_ACCESS}),
    )

    issues = check(modest, OFFERED)

    assert [issue.severity for issue in issues] == [Severity.WARNING]
    assert "CODE" in issues[0].message
    assert "will not be found" in issues[0].message


def test_an_employee_that_declares_nothing_is_told_so_once() -> None:
    issues = check(employee(), OFFERED)

    assert [issue.severity for issue in issues] == [Severity.WARNING]
    assert "can only think" in issues[0].message


# --- Reporting ----------------------------------------------------------------


def test_errors_come_before_warnings() -> None:
    # Claims CODE with no tool that runs any (an error), and holds fs.read
    # without declaring FILE_ACCESS (a warning).
    both = employee(tools=frozenset({"fs.read"}), capabilities=frozenset({Capability.CODE}))

    issues = check(both, OFFERED)

    assert [issue.severity for issue in issues] == [Severity.ERROR, Severity.WARNING]
    assert str(issues[0]).startswith("ERROR: worker: ")


def test_every_employee_is_checked() -> None:
    issues = check_all(
        [
            employee(name="a", capabilities=frozenset({Capability.CODE})),
            employee(name="b", capabilities=frozenset({Capability.CODE})),
        ],
        OFFERED,
    )

    assert {issue.employee for issue in issues} == {"a", "b"}
