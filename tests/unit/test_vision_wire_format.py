"""Putting a picture in front of a model, over the wire nobody opens a socket to."""

from __future__ import annotations

import base64
import json

import httpx

from domain.computer.models import Screenshot
from domain.llm.models import ImageContent, LLMRequest, Message
from infrastructure.llm.openrouter import OpenRouterProvider
from infrastructure.llm.retry import RetryPolicy
from tests.fakes.computer import png_bytes

COMPLETION = {
    "model": "vendor/eyes",
    "choices": [{"message": {"content": "A login page."}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 900, "completion_tokens": 4},
}


def capture() -> tuple[list[dict], OpenRouterProvider]:
    sent: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=COMPLETION)

    return sent, OpenRouterProvider(
        "test-key",
        default_model="vendor/eyes",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        retry_policy=RetryPolicy(attempts=1),
    )


async def test_a_message_with_a_picture_is_sent_as_content_parts() -> None:
    sent, provider = capture()
    shot = Screenshot(image=png_bytes(), width=64, height=48)

    await provider.generate(
        LLMRequest(
            messages=(
                Message.user("What is this?", images=(ImageContent(shot.as_data_url()),)),
            )
        )
    )

    content = sent[0]["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "What is this?"}
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


async def test_a_message_without_pictures_stays_a_plain_string() -> None:
    """Enough servers reject the list shape for a text-only turn to be worth the branch."""
    sent, provider = capture()

    await provider.generate(LLMRequest(messages=(Message.user("Which city?"),)))

    assert sent[0]["messages"][0]["content"] == "Which city?"


def test_a_screenshot_encodes_itself_so_no_two_adapters_disagree_about_how() -> None:
    image = png_bytes(4, 4)
    shot = Screenshot(image=image, width=4, height=4)

    prefix, payload = shot.as_data_url().split(",", 1)

    assert prefix == "data:image/png;base64"
    assert base64.b64decode(payload) == image
