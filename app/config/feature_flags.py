"""Flags for capabilities that arrive in later phases.

Each one is off until the phase that implements it lands, so a half-built
capability can sit in the tree without being reachable. Once the phase lands,
the flag stays as the switch that turns the capability off on a machine where
it is not wanted - Phase 5's DoD depends on exactly that.
"""

from __future__ import annotations

from pydantic import BaseModel


class FeatureFlags(BaseModel):
    browser_tools: bool = True  # Phase 4
    code_execution: bool = True  # Phase 4
    approvals: bool = True  # Phase 4
    computer_use: bool = False  # Phase 5
    kai_manager: bool = False  # Phase 7
    workflows: bool = False  # Phase 7
    scheduler: bool = False  # Phase 12
