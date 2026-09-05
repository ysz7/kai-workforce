"""Local-first configuration.

Provider keys and paths, and nothing else. Anything that would only make sense
with a server behind it does not belong here.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config.feature_flags import FeatureFlags


def _default_data_dir() -> Path:
    return Path.home() / ".kai-workforce"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="KAI_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # --- Paths ---------------------------------------------------------------
    data_dir: Path = Field(default_factory=_default_data_dir)
    database_url: str | None = None

    # --- Provider access -----------------------------------------------------
    llm_api_key: str | None = None
    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_default_model: str = "anthropic/claude-sonnet-5"

    # --- Runtime -------------------------------------------------------------
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] = "json"
    #: Language the agents answer the user in. Response language is configuration,
    #: never text hard-coded into the sources.
    response_language: str = "en"

    flags: FeatureFlags = Field(default_factory=FeatureFlags)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "kai.db"

    @property
    def resolved_database_url(self) -> str:
        """SQLite by default: one file, no server between `clone` and `run`."""
        if self.database_url:
            return self.database_url
        return f"sqlite+aiosqlite:///{self.db_path}"

    def ensure_data_dir(self) -> Path:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
