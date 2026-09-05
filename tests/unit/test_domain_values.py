from __future__ import annotations

from domain.capabilities.models import Capability, CapabilityRequirement
from domain.employees.definition import EmployeeDefinition, Goal, Role
from domain.llm.models import ModelProfile
from domain.policies.models import ActorKind, effective_tools
from domain.workspace.models import DEFAULT_WORKSPACE_ID, WorkspaceScope
from tests.fakes.actors import employee, kai


def test_local_workspace_is_the_default() -> None:
    assert WorkspaceScope.local().workspace_id == DEFAULT_WORKSPACE_ID
    assert WorkspaceScope().workspace_id == DEFAULT_WORKSPACE_ID


def test_capability_requirement_matches_and_ranks() -> None:
    requirement = CapabilityRequirement(
        required=frozenset({Capability.TOOL_CALLING}),
        preferred=frozenset({Capability.LONG_CONTEXT, Capability.VISION}),
    )

    assert not requirement.is_satisfied_by(frozenset({Capability.VISION}))
    assert requirement.is_satisfied_by(frozenset({Capability.TOOL_CALLING}))
    assert requirement.score(frozenset({Capability.VISION})) == -1
    assert requirement.score(frozenset({Capability.TOOL_CALLING})) == 0
    assert (
        requirement.score(frozenset({Capability.TOOL_CALLING, Capability.LONG_CONTEXT})) == 1
    )


def test_employee_definition_is_an_actor() -> None:
    definition = EmployeeDefinition.create(
        "researcher",
        Role("Research Specialist"),
        goals=(Goal("Find and verify sources"),),
        allowed_tools=frozenset({"browser.search"}),
    )

    assert definition.actor_kind is ActorKind.EMPLOYEE
    assert definition.actor_id == str(definition.id)


def test_definition_hash_tracks_the_declaration_not_the_identity() -> None:
    first = EmployeeDefinition.create("researcher", Role("Research Specialist"))
    same = EmployeeDefinition.create("researcher", Role("Research Specialist"))
    changed = EmployeeDefinition.create(
        "researcher", Role("Research Specialist"), allowed_tools=frozenset({"browser.search"})
    )

    assert first.definition_hash == same.definition_hash
    assert first.definition_hash != changed.definition_hash


def test_model_profile_states_requirements_not_vendors() -> None:
    profile = ModelProfile(capabilities=frozenset({Capability.CODE}), min_context_tokens=100_000)
    requirement = profile.as_requirement()

    assert requirement.required == frozenset({Capability.CODE})
    assert requirement.min_context_tokens == 100_000


def test_delegation_does_not_escalate_privileges() -> None:
    manager = kai("browser.search", "fs.write", "email.send")
    executor = employee("researcher", "browser.search", "fs.read")

    assert effective_tools(manager, executor) == frozenset({"browser.search"})
