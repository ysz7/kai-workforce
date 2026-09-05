"""Loads employee declarations from `employees/*/employee.yaml`.

This is where "an employee is a declaration, not code" is actually enforced. If
adding an employee ever requires touching a Python file, it will be this one -
and that would be the bug.

It lives in `infrastructure/` rather than `application/` for the same reason the
task repository does: it reads from disk. The plan sketches it under
`application/workforce/`, but the layering rule it also states - application
depends on the domain only - puts file I/O here.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid5

import yaml

from domain.capabilities.models import Capability, CapabilityRequirement
from domain.employees.definition import EmployeeDefinition, Goal, Role
from domain.employees.limits import ExecutionLimits
from domain.errors import ConfigurationError, EmployeeNotFoundError
from domain.llm.models import ModelProfile
from domain.memory.models import MemoryScope
from domain.workspace.models import DEFAULT_WORKSPACE_ID, WorkspaceId
from infrastructure.observability.logging import get_logger

log = get_logger(__name__)

DEFAULT_EMPLOYEES_DIR = Path(__file__).resolve().parents[2] / "employees"

#: Employee ids are derived from the name rather than generated, so the same
#: declaration keeps the same identity across restarts and across machines -
#: which is what makes assignment history survive a reinstall.
EMPLOYEE_NAMESPACE = UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")


def employee_id_for(name: str, workspace_id: WorkspaceId = DEFAULT_WORKSPACE_ID) -> UUID:
    return uuid5(EMPLOYEE_NAMESPACE, f"{workspace_id}/{name}")


class YamlEmployeeRegistry:
    """Implements `domain.employees.protocols.EmployeeRegistry`."""

    def __init__(
        self,
        directory: Path | None = None,
        workspace_id: WorkspaceId = DEFAULT_WORKSPACE_ID,
    ) -> None:
        self._directory = directory or DEFAULT_EMPLOYEES_DIR
        self._workspace_id = workspace_id
        self._definitions: dict[str, EmployeeDefinition] | None = None

    # --- Discovery ------------------------------------------------------------

    def _load(self) -> dict[str, EmployeeDefinition]:
        if self._definitions is not None:
            return self._definitions

        definitions: dict[str, EmployeeDefinition] = {}
        for path in sorted(self._directory.glob("*/employee.yaml")):
            definition = self._parse(path)
            if definition.name in definitions:
                raise ConfigurationError(
                    f"Two employees are called '{definition.name}'; names must be unique"
                )
            definitions[definition.name] = definition

        self._definitions = definitions
        log.info("employees.loaded", count=len(definitions), names=sorted(definitions))
        return definitions

    def _parse(self, path: Path) -> EmployeeDefinition:
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as error:
            raise ConfigurationError(f"{path} is not valid YAML: {error}") from error

        try:
            name = str(raw["name"])
            role = Role(
                title=str(raw["role"]), description=str(raw.get("role_description", "")).strip()
            )
        except KeyError as error:
            raise ConfigurationError(f"{path} is missing required field {error}") from error

        profile = raw.get("model_profile") or {}
        try:
            model_profile = ModelProfile(
                capabilities=frozenset(
                    Capability(c) for c in profile.get("capabilities", ["TEXT_REASONING"])
                ),
                min_context_tokens=profile.get("min_context_tokens"),
                max_cost_per_1k_usd=profile.get("max_cost_per_1k_usd"),
                temperature=float(profile.get("temperature", 0.2)),
            )
            memory_scope = MemoryScope(raw.get("memory_scope", MemoryScope.EMPLOYEE_PRIVATE))
        except ValueError as error:
            raise ConfigurationError(f"{path}: {error}") from error

        limits_raw = raw.get("limits") or {}
        limits = ExecutionLimits(
            max_steps=int(limits_raw.get("max_steps", 12)),
            max_cost_usd=float(limits_raw.get("max_cost_usd", 1.0)),
            max_wall_time_seconds=float(limits_raw.get("max_wall_time_seconds", 600.0)),
        )

        prompt = path.parent / "prompts" / "system.md"
        definition = EmployeeDefinition(
            id=employee_id_for(name, self._workspace_id),
            name=name,
            role=role,
            goals=tuple(
                Goal(text=str(g["text"]), priority=int(g.get("priority", 5)))
                if isinstance(g, dict)
                else Goal(text=str(g))
                for g in raw.get("goals", ())
            ),
            allowed_tools=frozenset(raw.get("allowed_tools") or ()),
            policies=frozenset(raw.get("policies") or ()),
            model_profile=model_profile,
            memory_scope=memory_scope,
            limits=limits,
            system_prompt=(
                prompt.read_text(encoding="utf-8").strip() if prompt.exists() else ""
            ),
            workspace_id=self._workspace_id,
            enabled=bool(raw.get("enabled", True)),
        )
        return definition

    # --- EmployeeRegistry -----------------------------------------------------

    def list(self, workspace: WorkspaceId = DEFAULT_WORKSPACE_ID) -> list[EmployeeDefinition]:
        return [
            definition
            for definition in self._load().values()
            if definition.workspace_id == workspace and definition.enabled
        ]

    def get(self, name: str) -> EmployeeDefinition:
        definition = self._load().get(name)
        if definition is None:
            known = ", ".join(sorted(self._load())) or "none"
            raise EmployeeNotFoundError(f"{name}. Declared employees: {known}")
        return definition

    def find_by_capability(
        self, requirement: CapabilityRequirement
    ) -> list[EmployeeDefinition]:
        """Which employees could do work with these requirements.

        Matched against what the employee's model profile offers. It is how KAI
        will find a new employee in Phase 7 without anyone editing KAI.
        """
        return [
            definition
            for definition in self.list()
            if requirement.is_satisfied_by(definition.model_profile.capabilities)
        ]
