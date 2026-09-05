from __future__ import annotations

import pytest
import structlog

from infrastructure.observability.logging import configure_logging, correlation_context


@pytest.fixture(autouse=True)
def _configured() -> None:
    configure_logging("INFO", "json")


def test_correlation_ids_are_bound_and_released() -> None:
    with correlation_context(task_id="t-1") as correlation_id:
        bound = structlog.contextvars.get_contextvars()
        assert bound["task_id"] == "t-1"
        assert bound["correlation_id"] == correlation_id

    assert structlog.contextvars.get_contextvars() == {}


def test_an_explicit_correlation_id_is_kept() -> None:
    with correlation_context(correlation_id="abc", objective_id="o-1") as correlation_id:
        assert correlation_id == "abc"


def test_a_misspelled_key_fails_loudly() -> None:
    # A silently dropped id only shows up when someone tries to read a trace.
    with pytest.raises(ValueError, match="taks_id"), correlation_context(taks_id="t-1"):
        pass
