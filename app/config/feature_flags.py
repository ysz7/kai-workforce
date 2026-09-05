"""Flags for capabilities that arrive in later phases.

Each one is off until the phase that implements it lands, so a half-built
capability can sit in the tree without being reachable.
"""

from __future__ import annotations

from pydantic import BaseModel


class FeatureFlags(BaseModel):
    browser_tools: bool = False  # Phase 4
    computer_use: bool = False  # Phase 5
    approvals: bool = False  # Phase 4
    kai_manager: bool = False  # Phase 7
    workflows: bool = False  # Phase 7
    scheduler: bool = False  # Phase 12
