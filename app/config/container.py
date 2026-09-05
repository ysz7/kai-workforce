"""The composition root: settings meet the container here and nowhere else."""

from __future__ import annotations

from app.config.settings import Settings, get_settings
from infrastructure.container import Container


def build_container(settings: Settings | None = None, *, in_memory: bool = False) -> Container:
    return Container(settings or get_settings(), in_memory=in_memory)
