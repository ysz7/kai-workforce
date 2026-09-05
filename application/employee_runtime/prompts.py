"""Prompt templates, loaded from files and versioned there.

Prompts are content, not code: they change far more often than the loop around
them, and a diff on a `.md` file is readable in a way that a diff on an embedded
triple-quoted string is not.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from domain.errors import ConfigurationError

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


@lru_cache(maxsize=32)
def load(name: str, version: str = "v1") -> str:
    path = PROMPTS_DIR / name / f"{version}.md"
    if not path.exists():
        raise ConfigurationError(f"Prompt not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def render(name: str, version: str = "v1", **values: object) -> str:
    template = load(name, version)
    try:
        return template.format(**values)
    except KeyError as error:
        raise ConfigurationError(
            f"Prompt {name}/{version} references {error} but it was not supplied"
        ) from error
