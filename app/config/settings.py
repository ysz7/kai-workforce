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
    #: Override the bundled model catalog. Changing models is a config change.
    model_catalog_path: Path | None = None
    #: Where employee declarations are discovered. Adding an employee is adding
    #: a directory here, and nothing else.
    employees_dir: Path | None = None
    #: How long to wait on a model. Unset means each provider's own default,
    #: which differs for a reason: a hosted model that has not answered in two
    #: minutes is not going to, and a model running on this laptop is often only
    #: halfway through. Set it when you know better than both.
    llm_timeout_seconds: float | None = None
    llm_retry_attempts: int = 3
    #: Where a locally served model listens. Used only by the 'local' provider.
    local_llm_base_url: str = "http://127.0.0.1:11434/v1"

    # --- Tools ---------------------------------------------------------------
    #: The one directory the filesystem tools can see. Point it at the folder
    #: the work is actually in; nothing outside it is reachable.
    workspace_dir: Path | None = None
    #: prompt | deny | allow. What happens when an irreversible action comes up:
    #: ask the person at the terminal, refuse, or - only if explicitly set -
    #: proceed. A run with nobody watching refuses whatever this says.
    approval_mode: Literal["prompt", "deny", "allow"] = "prompt"
    browser_headless: bool = True
    browser_timeout_seconds: float = 30.0
    code_timeout_seconds: float = 30.0

    # --- Computer use --------------------------------------------------------
    #: Applications the desktop surface may act in. Empty means none: acting on
    #: the machine is opt-in per application, the way the filesystem tools are
    #: opt-in per directory. Ignored by the browser surface, which has no
    #: applications to choose between.
    computer_allowed_applications: tuple[str, ...] = ()
    #: The part of the screen that may be touched, as "WIDTHxHEIGHT+X+Y".
    #: Unset means the whole of it.
    computer_allowed_region: str | None = None
    #: A budget for actions on a screen, separate from the run's step limit:
    #: one step of the loop can ask for several clicks.
    computer_max_actions: int = 200

    # --- Local interface -----------------------------------------------------
    #: The loopback address, and not configurable to anything else by accident.
    #: This interface starts tasks and approves irreversible actions; it has no
    #: authentication because it is not reachable, and binding it elsewhere
    #: would quietly turn a local tool into an unauthenticated remote one.
    ui_host: str = "127.0.0.1"
    ui_port: int = 8765
    #: How long an irreversible action waits for someone to answer in the
    #: interface before it is refused.
    ui_approval_timeout_seconds: float = 600.0
    #: How many past tasks the history list loads.
    ui_history_limit: int = 50

    # --- Runtime -------------------------------------------------------------
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] = "json"
    #: Language the agents answer the user in. Response language is configuration,
    #: never text hard-coded into the sources.
    response_language: str = "en"

    flags: FeatureFlags = Field(default_factory=FeatureFlags)

    @property
    def resolved_workspace_dir(self) -> Path:
        """Where the employees' files live, separate from the platform's own."""
        return self.workspace_dir or (self.data_dir / "workspace")

    @property
    def browser_tools_enabled(self) -> bool:
        return self.flags.browser_tools

    @property
    def code_execution_enabled(self) -> bool:
        return self.flags.code_execution

    @property
    def approvals_enabled(self) -> bool:
        return self.flags.approvals

    @property
    def computer_use_enabled(self) -> bool:
        """Phase 5's Definition of Done rests on this being a switch.

        Off, the computer tools are not registered at all - and every scenario
        with an API or a browser path keeps working, because those are different
        tools at a different level of the hierarchy.
        """
        return self.flags.computer_use

    @property
    def stop_file_path(self) -> Path:
        """The brake. `kai stop` writes it; every screen action reads it."""
        return self.data_dir / "STOP"

    def ensure_workspace_dir(self) -> Path:
        directory = self.resolved_workspace_dir
        directory.mkdir(parents=True, exist_ok=True)
        return directory

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
