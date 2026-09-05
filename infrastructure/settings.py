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

    @property
    def resolved_database_url(self) -> str: ...

    def ensure_data_dir(self) -> Path: ...
