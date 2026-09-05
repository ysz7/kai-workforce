"""Secrets: resolved at the point of use, and never in anything that is stored."""

from __future__ import annotations

import pytest

from domain.errors import SecretNotFoundError
from domain.secrets.models import Secret, redact
from domain.tools.telemetry import ToolCallRecord
from infrastructure.secrets.env import EnvSecretResolver


def test_a_secret_does_not_print_itself() -> None:
    secret = Secret("search_key", "sk-live-1234")

    assert str(secret) == "***"
    assert "sk-live" not in repr(secret)
    assert "sk-live" not in f"{secret}"
    assert secret.reveal() == "sk-live-1234"


def test_the_platform_prefix_wins_over_a_bare_variable() -> None:
    resolver = EnvSecretResolver({"KAI_SECRET_TOKEN": "scoped", "TOKEN": "global"})

    assert resolver.get("token").reveal() == "scoped"


def test_an_existing_variable_is_used_when_there_is_no_scoped_one() -> None:
    assert EnvSecretResolver({"TOKEN": "global"}).get("token").reveal() == "global"


def test_a_missing_credential_says_which_variable_to_set() -> None:
    with pytest.raises(SecretNotFoundError, match="KAI_SECRET_TOKEN"):
        EnvSecretResolver({}).get("token")


def test_maybe_is_for_the_optional_case() -> None:
    assert EnvSecretResolver({}).maybe("token") is None


@pytest.mark.parametrize(
    "key", ["api_key", "API_KEY", "authorization", "x_access_token", "password"]
)
def test_anything_named_like_a_credential_is_masked(key: str) -> None:
    assert redact({key: "sk-live"}) == {key: "***"}


def test_redaction_reaches_into_nested_structures() -> None:
    redacted = redact({"headers": [{"authorization": "Bearer x"}], "url": "https://x"})

    assert redacted == {"headers": [{"authorization": "***"}], "url": "https://x"}


def test_a_stored_tool_call_carries_no_credential() -> None:
    record = ToolCallRecord(
        tool="api.send",
        success=True,
        input_data={"url": "https://x", "api_key": "sk-live"},
        output={"token": "t-1"},
    )

    safe = record.redacted()

    assert safe.input_data == {"url": "https://x", "api_key": "***"}
    assert safe.output == {"token": "***"}
