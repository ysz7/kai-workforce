"""The architecture rules, checked as tests rather than trusted as convention.

import-linter enforces the same contracts in CI; these tests fail faster and
say plainly what broke.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

FORBIDDEN_IN_DOMAIN = {
    "app",
    "application",
    "infrastructure",
    "sqlalchemy",
    "alembic",
    "httpx",
    "openai",
    "anthropic",
    "playwright",
    "typer",
    "structlog",
    "pydantic_settings",
}

FORBIDDEN_IN_KAI = {"infrastructure", "app", "employees"}


def imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def python_files(package: str) -> list[Path]:
    return sorted((REPO_ROOT / package).rglob("*.py"))


def test_domain_imports_nothing_but_the_standard_library() -> None:
    offenders = {
        str(path.relative_to(REPO_ROOT)): sorted(imported_roots(path) & FORBIDDEN_IN_DOMAIN)
        for path in python_files("domain")
    }
    offenders = {path: roots for path, roots in offenders.items() if roots}
    assert not offenders, f"domain must not depend on infrastructure: {offenders}"


def test_application_does_not_import_infrastructure() -> None:
    offenders = {
        str(path.relative_to(REPO_ROOT)): sorted(
            imported_roots(path) & {"infrastructure", "app"}
        )
        for path in python_files("application")
    }
    offenders = {path: roots for path, roots in offenders.items() if roots}
    assert not offenders, f"application talks to domain contracts only: {offenders}"


def test_kai_never_imports_a_concrete_employee_or_adapter() -> None:
    kai_dir = REPO_ROOT / "application" / "kai"
    offenders = {
        str(path.relative_to(REPO_ROOT)): sorted(imported_roots(path) & FORBIDDEN_IN_KAI)
        for path in sorted(kai_dir.rglob("*.py"))
    }
    offenders = {path: roots for path, roots in offenders.items() if roots}
    assert not offenders, f"KAI knows employees only through the registry: {offenders}"


def test_sql_does_not_leave_the_persistence_package() -> None:
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for package in ("domain", "application", "app")
        for path in python_files(package)
        if "sqlalchemy" in imported_roots(path)
    ]
    assert not offenders, f"SQL must stay inside infrastructure/persistence: {offenders}"


def test_the_boundary_check_would_actually_catch_a_violation(tmp_path) -> None:
    """Guard the guard: a checker that never fails proves nothing."""
    offender = tmp_path / "leaky.py"
    offender.write_text("import httpx\nfrom sqlalchemy import select\n", encoding="utf-8")

    assert imported_roots(offender) & FORBIDDEN_IN_DOMAIN == {"httpx", "sqlalchemy"}
