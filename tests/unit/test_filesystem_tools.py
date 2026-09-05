"""Files: what the tools do, and what they refuse to do."""

from __future__ import annotations

from pathlib import Path

import pytest

from domain.policies.models import RiskLevel
from infrastructure.tools.filesystem import (
    FileListTool,
    FileMoveTool,
    FileReadTool,
    FileWriteTool,
    Workspace,
)


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "notes.txt").write_text("hello", encoding="utf-8")
    (root / "invoices").mkdir()
    return Workspace(root)


async def test_a_file_inside_the_workspace_is_read(workspace: Workspace) -> None:
    result = await FileReadTool(workspace).execute({"path": "notes.txt"})

    assert result.success
    assert result.output["content"] == "hello"
    assert result.output["truncated"] is False


async def test_a_path_escaping_the_workspace_is_refused(workspace: Workspace) -> None:
    result = await FileReadTool(workspace).execute({"path": "../../.ssh/id_rsa"})

    assert not result.success
    assert "outside the working directory" in result.error


async def test_a_symlink_out_of_the_workspace_is_refused(workspace: Workspace, tmp_path) -> None:
    """Resolved before the check: the escape is only visible once symlinks are followed."""
    secret = tmp_path / "secret.txt"
    secret.write_text("token", encoding="utf-8")
    (workspace.root / "innocent.txt").symlink_to(secret)

    result = await FileReadTool(workspace).execute({"path": "innocent.txt"})

    assert not result.success
    assert "outside the working directory" in result.error


async def test_a_large_file_is_read_in_parts(workspace: Workspace) -> None:
    (workspace.root / "big.txt").write_text("x" * 50, encoding="utf-8")
    tool = FileReadTool(workspace, max_bytes=10)

    first = await tool.execute({"path": "big.txt"})
    assert first.output["truncated"] is True
    assert first.output["bytes_read"] == 10

    rest = await tool.execute({"path": "big.txt", "offset": 45})
    assert rest.output["truncated"] is False


async def test_listing_reports_paths_relative_to_the_workspace(workspace: Workspace) -> None:
    result = await FileListTool(workspace).execute({"path": "."})

    paths = {entry["path"] for entry in result.output["entries"]}
    assert paths == {"notes.txt", "invoices"}
    assert all(not path.startswith("/") for path in paths)


async def test_listing_can_filter_and_descend(workspace: Workspace) -> None:
    (workspace.root / "invoices" / "march.pdf").write_bytes(b"%PDF")

    result = await FileListTool(workspace).execute({"pattern": "*.pdf", "recursive": True})

    assert [entry["path"] for entry in result.output["entries"]] == ["invoices/march.pdf"]


async def test_writing_a_new_file_creates_missing_directories(workspace: Workspace) -> None:
    result = await FileWriteTool(workspace).execute(
        {"path": "reports/2026/summary.md", "content": "done"}
    )

    assert result.success
    assert (workspace.root / "reports/2026/summary.md").read_text() == "done"
    assert result.output["overwritten"] is False


async def test_writing_a_new_file_is_low_risk_and_overwriting_is_not(workspace: Workspace) -> None:
    """The same tool, two different actions. Only one of them needs a person."""
    tool = FileWriteTool(workspace)

    assert tool.assess({"path": "fresh.md"}).risk_level is RiskLevel.LOW
    assert tool.assess({"path": "notes.txt"}).risk_level is RiskLevel.HIGH


async def test_moving_into_a_directory_keeps_the_file_name(workspace: Workspace) -> None:
    result = await FileMoveTool(workspace).execute(
        {"source": "notes.txt", "destination": "invoices"}
    )

    assert result.output["destination"] == "invoices/notes.txt"
    assert (workspace.root / "invoices" / "notes.txt").exists()


async def test_moving_onto_an_existing_file_needs_a_person(workspace: Workspace) -> None:
    (workspace.root / "invoices" / "notes.txt").write_text("older", encoding="utf-8")
    tool = FileMoveTool(workspace)

    assessment = tool.assess({"source": "notes.txt", "destination": "invoices/notes.txt"})

    assert assessment.risk_level is RiskLevel.HIGH


async def test_sorting_a_folder_does_not_ask_a_question_per_file(workspace: Workspace) -> None:
    # A move to a free name is undone by another move, so it is not gated.
    assessment = FileMoveTool(workspace).assess(
        {"source": "notes.txt", "destination": "invoices/renamed.txt"}
    )

    assert assessment.risk_level is RiskLevel.LOW


async def test_moving_something_that_is_not_there_is_reported_not_raised(
    workspace: Workspace,
) -> None:
    result = await FileMoveTool(workspace).execute({"source": "ghost.txt", "destination": "x.txt"})

    assert not result.success
    assert "does not exist" in result.error
