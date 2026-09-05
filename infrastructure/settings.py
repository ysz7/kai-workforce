"""What infrastructure needs from configuration, and nothing more.

`Settings` itself lives in `app/config/`, which is the composition root's
business. Infrastructure states its requirement as a Protocol instead of
importing upwards, so the layering rule holds: `infrastructure -> domain` only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class RuntimeSettings(Protocol):
    data_dir: Path
    log_level: str
    log_format: str

    # --- Model access ---------------------------------------------------------
    llm_api_key: str | None
    llm_base_url: str
    model_catalog_path: Path | None
    employees_dir: Path | None
    llm_timeout_seconds: float
    llm_retry_attempts: int
    local_llm_base_url: str

    # --- Tools ----------------------------------------------------------------
    approval_mode: str
    browser_headless: bool
    browser_timeout_seconds: float
    code_timeout_seconds: float
    computer_allowed_applications: tuple[str, ...]
    computer_allowed_region: str | None
    computer_max_actions: int

    @property
    def resolved_database_url(self) -> str: ...

    @property
    def resolved_workspace_dir(self) -> Path: ...

    @property
    def browser_tools_enabled(self) -> bool: ...

    @property
    def code_execution_enabled(self) -> bool: ...

    @property
    def approvals_enabled(self) -> bool: ...

    @property
    def computer_use_enabled(self) -> bool: ...

    @property
    def stop_file_path(self) -> Path: ...

    def ensure_data_dir(self) -> Path: ...

    def ensure_workspace_dir(self) -> Path: ...
