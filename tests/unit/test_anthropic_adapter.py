"""The Messages API wire format, checked without a network or a key.

Every assertion here is about a difference from the chat-completions shape the
other adapters speak. They are not cosmetic: three of them are a 400 rather than
a worse answer, and one of them silently describes a different conversation to
the model.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from domain.errors import InvalidRequestError, ProviderUnavailableError, RateLimitError
from domain.llm.models import (
    FinishReason,
    ImageContent,
    LLMRequest,
    Message,
    ToolCallRequest,
)
from domain.tools.models import ToolSpec
from domain.tools.schema import Param
from infrastructure.llm.anthropic import API_VERSION, AnthropicProvider
from infrastructure.llm.retry import RetryPolicy

ANSWER = {
    "id": "msg_1",
    "model": "claude-haiku-4-5",
    "content": [{"type": "text", "text": "Forty-one."}],
    "stop_reason": "end_turn",
    "usage": {"input_tokens": 12, "output_tokens": 3},
}


def provider(
    handler, *, model: str = "claude-haiku-4-5", **kwargs
) -> tuple[AnthropicProvider, list[dict[str, Any]]]:
    """A provider whose transport is a function, so nothing leaves the process."""
    sent: list[dict[str, Any]] = []

    def _handle(request: httpx.Request) -> httpx.Response:
        import json

        sent.append(
            {
                "url": str(request.url),
                "headers": dict(request.headers),
                "body": json.loads(request.content),
            }
        )
        return handler(sent[-1]["body"])

    client = httpx.AsyncClient(transport=httpx.MockTransport(_handle))
    return (
        AnthropicProvider(
            "sk-ant-test",
            default_model=model,
            client=client,
            retry_policy=RetryPolicy(attempts=1),
            **kwargs,
        ),
        sent,
    )


def ok(_: dict[str, Any]) -> httpx.Response:
    return httpx.Response(200, json=ANSWER)


# --- The request ---------------------------------------------------------------


async def test_the_system_prompt_is_lifted_out_of_the_transcript() -> None:
    """A system turn is a top-level field here, not a message with a role."""
    llm, sent = provider(ok)

    await llm.generate(
        LLMRequest(
            messages=(
                Message.system("You are terse."),
                Message.system("Answer in one line."),
                Message.user("How many?"),
            )
        )
    )

    body = sent[0]["body"]
    assert body["system"] == "You are terse.\n\nAnswer in one line."
    assert [m["role"] for m in body["messages"]] == ["user"]


async def test_the_required_headers_are_sent() -> None:
    llm, sent = provider(ok)
    await llm.generate(LLMRequest(messages=(Message.user("hello"),)))

    headers = sent[0]["headers"]
    assert headers["x-api-key"] == "sk-ant-test"
    assert headers["anthropic-version"] == API_VERSION
    assert sent[0]["url"].endswith("/v1/messages")
    assert "authorization" not in headers, "the key goes in x-api-key, not a bearer token"


async def test_max_tokens_is_always_sent_because_it_is_required() -> None:
    llm, sent = provider(ok)
    await llm.generate(LLMRequest(messages=(Message.user("hello"),)))
    assert sent[0]["body"]["max_tokens"] > 0

    await llm.generate(LLMRequest(messages=(Message.user("hello"),), max_tokens=64))
    assert sent[1]["body"]["max_tokens"] == 64


async def test_temperature_goes_only_to_models_that_still_accept_it() -> None:
    """Sampling was removed on the current top models: sending it is a 400."""
    haiku, sent = provider(ok, model="claude-haiku-4-5")
    await haiku.generate(LLMRequest(messages=(Message.user("x"),), temperature=0.4))
    assert sent[0]["body"]["temperature"] == 0.4

    newer, sent = provider(ok, model="claude-sonnet-5")
    await newer.generate(LLMRequest(messages=(Message.user("x"),), temperature=0.4))
    assert "temperature" not in sent[0]["body"]


async def test_the_json_response_format_is_dropped_rather_than_guessed_at() -> None:
    """It has no equivalent here, and an unknown field is a 400 for no gain."""
    llm, sent = provider(ok)

    await llm.generate(
        LLMRequest(
            messages=(Message.user("give me json"),),
            response_format={"type": "json_object"},
        )
    )

    assert "response_format" not in sent[0]["body"]
    assert "output_config" not in sent[0]["body"]


async def test_a_tool_is_declared_flat_not_wrapped_in_a_function() -> None:
    llm, sent = provider(ok)
    spec = ToolSpec.of("fs.read", "Read a file.", Param("path", description="Which file."))

    await llm.generate(LLMRequest(messages=(Message.user("read it"),), tools=(spec,)))

    tool = sent[0]["body"]["tools"][0]
    assert tool["name"] == "fs_read", "a dot in a tool name is a 400"
    assert tool["description"] == "Read a file."
    assert tool["input_schema"]["properties"]["path"]
    assert "function" not in tool


async def test_a_tool_result_is_a_content_block_on_a_user_message() -> None:
    llm, sent = provider(ok)

    await llm.generate(
        LLMRequest(
            messages=(
                Message.user("read a.txt"),
                Message.assistant(
                    "Reading it.",
                    tool_calls=(ToolCallRequest(id="t1", name="fs.read", arguments={"p": "a"}),),
                ),
                Message.tool("it says 41", "t1"),
            )
        )
    )

    user, assistant, result = sent[0]["body"]["messages"]
    assert user["role"] == "user"
    assert assistant["role"] == "assistant"
    assert assistant["content"] == [
        {"type": "text", "text": "Reading it."},
        # Named the same way the tool list is, or the model is shown a history
        # it could not have produced.
        {"type": "tool_use", "id": "t1", "name": "fs_read", "input": {"p": "a"}},
    ]
    assert result["role"] == "user", "a tool result is not a role of its own"
    assert result["content"] == [
        {"type": "tool_result", "tool_use_id": "t1", "content": "it says 41"}
    ]


async def test_two_tool_results_in_a_row_are_one_user_turn() -> None:
    """The quiet one: two turns describes a conversation that did not happen.

    A turn is everything that came back before the assistant spoke again. Split
    into two messages, the transcript says the assistant was asked twice.
    """
    llm, sent = provider(ok)

    await llm.generate(
        LLMRequest(
            messages=(
                Message.user("read both"),
                Message.assistant(
                    "",
                    tool_calls=(
                        ToolCallRequest(id="t1", name="fs.read", arguments={}),
                        ToolCallRequest(id="t2", name="fs.read", arguments={}),
                    ),
                ),
                Message.tool("first", "t1"),
                Message.tool("second", "t2"),
            )
        )
    )

    messages = sent[0]["body"]["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant", "user"]
    assert [block["tool_use_id"] for block in messages[-1]["content"]] == ["t1", "t2"]


async def test_an_assistant_turn_that_only_called_tools_carries_no_empty_text() -> None:
    llm, sent = provider(ok)

    await llm.generate(
        LLMRequest(
            messages=(
                Message.user("do it"),
                Message.assistant(
                    "", tool_calls=(ToolCallRequest(id="t1", name="fs.read", arguments={}),)
                ),
                Message.tool("done", "t1"),
            )
        )
    )

    assistant = sent[0]["body"]["messages"][1]
    assert [block["type"] for block in assistant["content"]] == ["tool_use"]


async def test_a_screenshot_is_sent_inline_as_base64() -> None:
    llm, sent = provider(ok)
    png = "iVBORw0KGgo="

    await llm.generate(
        LLMRequest(
            messages=(
                Message.user(
                    "what is on screen?",
                    images=(ImageContent(data_url=f"data:image/png;base64,{png}"),),
                ),
            )
        )
    )

    blocks = sent[0]["body"]["messages"][0]["content"]
    assert blocks[0]["type"] == "text"
    assert blocks[1] == {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png", "data": png},
    }


async def test_an_image_that_is_not_inline_is_dropped_with_a_warning() -> None:
    """Better a request without the picture than a 400 that loses the whole run."""
    llm, sent = provider(ok)

    await llm.generate(
        LLMRequest(
            messages=(
                Message.user("look", images=(ImageContent(data_url="https://x/y.png"),)),
            )
        )
    )

    assert [b["type"] for b in sent[0]["body"]["messages"][0]["content"]] == ["text"]


# --- The response --------------------------------------------------------------


async def test_text_and_usage_come_back_as_domain_values() -> None:
    llm, _ = provider(ok)

    response = await llm.generate(LLMRequest(messages=(Message.user("how many?"),)))

    assert response.content == "Forty-one."
    assert response.model == "claude-haiku-4-5"
    assert response.usage.prompt_tokens == 12, "input_tokens, not prompt_tokens"
    assert response.usage.output_tokens == 3
    assert response.finish_reason is FinishReason.STOP


async def test_a_tool_use_block_needs_no_json_decoding() -> None:
    """Its input is already an object, so there is nothing here that can fail."""

    def answer(_: dict[str, Any]) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "claude-haiku-4-5",
                "content": [
                    {"type": "text", "text": "Let me look."},
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "fs.read",
                        "input": {"path": "a.txt"},
                    },
                ],
                "stop_reason": "tool_use",
                "usage": {"input_tokens": 5, "output_tokens": 7},
            },
        )

    llm, _ = provider(answer)
    response = await llm.generate(LLMRequest(messages=(Message.user("read it"),)))

    assert response.content == "Let me look."
    assert response.finish_reason is FinishReason.TOOL_CALLS
    assert response.tool_calls == (
        ToolCallRequest(id="toolu_1", name="fs.read", arguments={"path": "a.txt"}),
    )


@pytest.mark.parametrize(
    ("stop_reason", "expected"),
    [
        ("end_turn", FinishReason.STOP),
        ("stop_sequence", FinishReason.STOP),
        ("pause_turn", FinishReason.STOP),
        ("max_tokens", FinishReason.LENGTH),
        ("tool_use", FinishReason.TOOL_CALLS),
        ("refusal", FinishReason.CONTENT_FILTER),
        ("something-new", FinishReason.STOP),
    ],
)
async def test_every_stop_reason_maps_to_something(stop_reason, expected) -> None:
    def answer(_: dict[str, Any]) -> httpx.Response:
        return httpx.Response(200, json={**ANSWER, "stop_reason": stop_reason})

    llm, _ = provider(answer)
    response = await llm.generate(LLMRequest(messages=(Message.user("x"),)))
    assert response.finish_reason is expected


async def test_several_text_blocks_are_joined() -> None:
    def answer(_: dict[str, Any]) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                **ANSWER,
                "content": [
                    {"type": "text", "text": "First."},
                    {"type": "thinking", "thinking": ""},
                    {"type": "text", "text": "Second."},
                ],
            },
        )

    llm, _ = provider(answer)
    response = await llm.generate(LLMRequest(messages=(Message.user("x"),)))
    assert response.content == "First.\nSecond."


# --- Failures ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (429, RateLimitError),
        (401, InvalidRequestError),
        (400, InvalidRequestError),
        (503, ProviderUnavailableError),
    ],
)
async def test_http_failures_become_the_domain_taxonomy(status, error) -> None:
    def answer(_: dict[str, Any]) -> httpx.Response:
        return httpx.Response(status, text='{"error": {"message": "no"}}')

    llm, _ = provider(answer)
    with pytest.raises(error):
        await llm.generate(LLMRequest(messages=(Message.user("x"),)))


async def test_an_unreadable_body_is_reported_as_the_providers_fault() -> None:
    from domain.errors import ProviderError

    def answer(_: dict[str, Any]) -> httpx.Response:
        return httpx.Response(200, json={"id": "msg_1"})

    llm, _ = provider(answer)
    with pytest.raises(ProviderError, match="unusable response"):
        await llm.generate(LLMRequest(messages=(Message.user("x"),)))


# --- Tool names ----------------------------------------------------------------


async def test_a_dotted_tool_name_is_translated_and_translated_back() -> None:
    """Every tool here is dotted and the API rejects a dot.

    Found by running it: the first real objective failed with
    `tools.0.custom.name: String should match pattern '^[a-zA-Z0-9_-]{1,128}$'`.
    The name has to come back as the executor knows it, or the call is refused
    as a tool the employee may not use.
    """

    def answer(body: dict[str, Any]) -> httpx.Response:
        assert [tool["name"] for tool in body["tools"]] == ["fs_read", "code_run"]
        return httpx.Response(
            200,
            json={
                **ANSWER,
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "fs_read", "input": {"path": "a"}}
                ],
                "stop_reason": "tool_use",
            },
        )

    llm, _ = provider(answer)
    response = await llm.generate(
        LLMRequest(
            messages=(Message.user("read it"),),
            tools=(
                ToolSpec.of("fs.read", "Read a file."),
                ToolSpec.of("code.run", "Run a script."),
            ),
        )
    )

    assert response.tool_calls[0].name == "fs.read", "the executor's name, not the wire one"


def test_two_names_that_would_collide_are_kept_apart() -> None:
    """Merging them would route a call to the wrong tool, silently."""
    from infrastructure.llm.anthropic import wire_names

    mapping = wire_names(["fs.read", "fs_read", "fs-read"])

    assert len(set(mapping.values())) == 3
    assert mapping["fs.read"] == "fs_read"
    assert mapping["fs_read"] != "fs_read"
    assert mapping["fs-read"] == "fs-read", "a hyphen is already legal"


def test_the_mapping_is_stable_for_the_same_tools() -> None:
    from infrastructure.llm.anthropic import wire_names

    names = ["fs.list", "fs.read", "web.search"]
    assert wire_names(names) == wire_names(names)
