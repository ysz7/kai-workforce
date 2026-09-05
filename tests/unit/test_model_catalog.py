from __future__ import annotations

import pytest

from domain.capabilities.models import Capability, CapabilityRequirement
from domain.errors import ConfigurationError
from domain.llm.models import TaskKind
from infrastructure.llm.catalog import DEFAULT_CATALOG_PATH, ModelCatalog

MINIMAL = {
    "models": {
        "one": {
            "provider": "openrouter",
            "model": "vendor/one",
            "capabilities": ["TEXT_REASONING"],
            "input_cost_per_1k_usd": 0.003,
            "output_cost_per_1k_usd": 0.015,
        }
    },
    "defaults": {"execution": "one"},
}


def test_the_bundled_catalog_loads_and_covers_every_task_kind() -> None:
    catalog = ModelCatalog.load(DEFAULT_CATALOG_PATH)
    assert catalog.entries
    missing = [kind for kind in TaskKind if kind not in catalog.defaults]
    assert not missing, f"no default model configured for: {missing}"


def test_cost_is_computed_per_thousand_tokens() -> None:
    entry = ModelCatalog.from_dict(MINIMAL).get("one")
    assert entry.cost_of(1000, 1000) == pytest.approx(0.018)
    assert entry.cost_of(500, 0) == pytest.approx(0.0015)


def test_candidates_respect_capabilities_and_context() -> None:
    catalog = ModelCatalog.from_dict(MINIMAL)
    assert catalog.candidates(CapabilityRequirement())
    assert not catalog.candidates(
        CapabilityRequirement(required=frozenset({Capability.VISION}))
    )
    assert not catalog.candidates(CapabilityRequirement(min_context_tokens=1_000_000))


def test_a_default_pointing_at_a_missing_model_is_rejected() -> None:
    broken = {"models": MINIMAL["models"], "defaults": {"execution": "nope"}}
    with pytest.raises(ConfigurationError, match="unknown model"):
        ModelCatalog.from_dict(broken)


def test_an_unknown_capability_is_rejected_rather_than_ignored() -> None:
    broken = {
        "models": {"one": {"provider": "p", "model": "m", "capabilities": ["TELEPATHY"]}}
    }
    with pytest.raises(ConfigurationError):
        ModelCatalog.from_dict(broken)


def test_an_empty_catalog_is_a_configuration_error() -> None:
    with pytest.raises(ConfigurationError, match="no models"):
        ModelCatalog.from_dict({"models": {}})


def test_a_missing_catalog_file_names_the_path(tmp_path) -> None:
    with pytest.raises(ConfigurationError, match="not found"):
        ModelCatalog.load(tmp_path / "absent.toml")
