"""The one place a tool is registered.

Adding a capability is a new file under `infrastructure/tools/` and a line in
this list. Nothing in `application/` learns the tool's name, no employee class
is edited, and whether an employee may call it is settled by its declaration -
so a tool nobody lists is a tool nobody can use, which is the intended default.

Building is lazy per group: a browser is not launched, and Playwright is not
imported, for a workforce whose employees only read files.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from domain.browser.protocols import Browser
from domain.search.protocols import SearchEngine
from domain.tools.protocols import Tool
from infrastructure.tools.code import CodeExecutionTool
from infrastructure.tools.filesystem import (
    FileListTool,
    FileMoveTool,
    FileReadTool,
    FileWriteTool,
    Workspace,
)
from infrastructure.tools.registry import InMemoryToolRegistry
from infrastructure.tools.web import BrowserExtractTool, BrowserOpenTool, WebSearchTool


def filesystem_tools(root: Path) -> list[Tool]:
    workspace = Workspace(root)
    workspace.ensure()
    return [
        FileListTool(workspace),
        FileReadTool(workspace),
        FileWriteTool(workspace),
        FileMoveTool(workspace),
    ]


def search_tools(engine: SearchEngine) -> list[Tool]:
    return [WebSearchTool(engine)]


def browser_tools(browser: Browser) -> list[Tool]:
    return [BrowserOpenTool(browser), BrowserExtractTool(browser)]


def code_tools(*, timeout_seconds: float = 30.0) -> list[Tool]:
    return [CodeExecutionTool(timeout_seconds=timeout_seconds)]


def build_registry(
    *,
    workspace_root: Path,
    search_engine: Callable[[], SearchEngine] | None = None,
    browser: Callable[[], Browser] | None = None,
    code_execution: bool = True,
    code_timeout_seconds: float = 30.0,
) -> InMemoryToolRegistry:
    """Everything this machine can do, before any employee's rights are applied."""
    tools: list[Tool] = list(filesystem_tools(workspace_root))
    if search_engine is not None:
        tools += search_tools(search_engine())
    if browser is not None:
        tools += browser_tools(browser())
    if code_execution:
        tools += code_tools(timeout_seconds=code_timeout_seconds)
    return InMemoryToolRegistry(tools)
