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
    llm_timeout_seconds: float
    llm_retry_attempts: int
    local_llm_base_url: str

    @property
    def resolved_database_url(self) -> str: ...

    def ensure_data_dir(self) -> Path: ...
