from __future__ import annotations

import pytest

from domain.errors import PermissionDeniedError, ToolNotFoundError
from infrastructure.tools.registry import InMemoryToolRegistry
from tests.fakes.actors import employee, kai, user
from tests.fakes.tools import FakeTool


@pytest.fixture
def registry() -> InMemoryToolRegistry:
    return InMemoryToolRegistry([FakeTool("fs.read"), FakeTool("fs.write"), FakeTool("fs.delete")])


def test_an_actor_only_sees_what_it_may_use(registry) -> None:
    researcher = employee("researcher", "fs.read")
    assert [spec.name for spec in registry.list_specs(researcher)] == ["fs.read"]


def test_nothing_is_granted_by_default(registry) -> None:
    # Least privilege: an actor that lists no tools gets none, rather than all.
    assert registry.list_specs(employee("newcomer")) == []


def test_a_permitted_tool_is_returned(registry) -> None:
    tool = registry.get("fs.read", employee("researcher", "fs.read"))
    assert tool.spec.name == "fs.read"


def test_a_forbidden_tool_is_refused_even_though_it_exists(registry) -> None:
    with pytest.raises(PermissionDeniedError, match=r"fs\.delete"):
        registry.get("fs.delete", employee("researcher", "fs.read"))


def test_an_unknown_tool_is_reported_as_missing_not_forbidden(registry) -> None:
    # The two are different problems and lead to different fixes.
    with pytest.raises(ToolNotFoundError):
        registry.get("fs.teleport", employee("researcher", "*"))


def test_a_wildcard_has_to_be_asked_for(registry) -> None:
    assert len(registry.list_specs(user("*"))) == 3
    assert registry.list_specs(user()) == []


def test_kai_is_not_privileged_by_being_kai(registry) -> None:
    # The manager is an actor like any other; delegation never escalates.
    with pytest.raises(PermissionDeniedError):
        registry.get("fs.delete", kai("fs.read"))


def test_re_registering_a_name_replaces_the_tool(registry) -> None:
    replacement = FakeTool("fs.read", description="A better reader")
    registry.register(replacement)

    assert registry.get("fs.read", user("*")).spec.description == "A better reader"
