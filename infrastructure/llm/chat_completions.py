"""The chat-completions wire format, shared by the providers that speak it.

Several very different services - a hosted router, a local model runner - expose
the same request and response shape. What they share is the format, not a
vendor, so that is what this module is named after and what it implements.

Providers subclass it to say who they are, where they live and whether they need
a key. Anything that genuinely differs on the wire (Anthropic's top-level system
field, Gemini's contents and parts) gets its own adapter instead of a flag here.
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from domain.errors import ProviderError
from domain.llm.models import (
    FinishReason,
    LLMRequest,
    LLMResponse,
    Message,
    Role,
    ToolCallRequest,
    Usage,
)
from domain.tools.models import ToolSpec
from infrastructure.llm.errors import translate_status, translate_transport_error
from infrastructure.llm.retry import RetryPolicy, with_retry
from infrastructure.observability.logging import get_logger

log = get_logger(__name__)

_FINISH_REASONS = {
    "stop": FinishReason.STOP,
    "length": FinishReason.LENGTH,
    "tool_calls": FinishReason.TOOL_CALLS,
    "content_filter": FinishReason.CONTENT_FILTER,
}


class ChatCompletionsProvider:
    """Implements `domain.llm.protocols.LLM` over `POST /chat/completions`."""

    #: Reported in errors and recorded against every call.
    provider_name: str = "chat-completions"

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str,
        default_model: str,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 120.0,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._default_model = default_model
        self._timeout = timeout_seconds
        self._retry_policy = retry_policy or RetryPolicy()
        self._client = client
        self._owns_client = client is None

    # --- Client lifecycle -----------------------------------------------------

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None

    # --- LLM ------------------------------------------------------------------

    async def generate(self, request: LLMRequest) -> LLMResponse:
        payload = self._to_payload(request)
        started = time.perf_counter()

        async def _call() -> dict[str, Any]:
            return await self._post("/chat/completions", payload)

        body = await with_retry(_call, self._retry_policy)
        latency_ms = int((time.perf_counter() - started) * 1000)
        return self._from_payload(body, latency_ms=latency_ms)

    # --- Wire format ----------------------------------------------------------

    def _to_payload(self, request: LLMRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model or self._default_model,
            "messages": [_message_to_wire(message) for message in request.messages],
            "temperature": request.temperature,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.tools:
            payload["tools"] = [_tool_to_wire(tool) for tool in request.tools]
        if request.response_format is not None:
            payload["response_format"] = request.response_format
        return payload

    def _from_payload(self, body: dict[str, Any], *, latency_ms: int) -> LLMResponse:
        try:
            choice = body["choices"][0]
            message = choice["message"]
        except (KeyError, IndexError, TypeError) as error:
            raise ProviderError(
                f"{self.provider_name} returned an unusable response: {body}"
            ) from error

        raw_usage = body.get("usage") or {}
        return LLMResponse(
            content=message.get("content") or "",
            model=body.get("model", self._default_model),
            tool_calls=tuple(_tool_call_from_wire(c) for c in message.get("tool_calls") or ()),
            usage=Usage(
                prompt_tokens=int(raw_usage.get("prompt_tokens", 0)),
                output_tokens=int(raw_usage.get("completion_tokens", 0)),
                latency_ms=latency_ms,
            ),
            finish_reason=_FINISH_REASONS.get(choice.get("finish_reason"), FinishReason.STOP),
        )

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        client = self._ensure_client()
        try:
            response = await client.post(
                f"{self._base_url}{path}",
                json=payload,
                headers=self._headers(),
                timeout=self._timeout,
            )
        except Exception as error:  # httpx transport failures
            raise translate_transport_error(error, provider=self.provider_name) from error

        if response.status_code >= 400:
            raise translate_status(
                response.status_code, response.text, provider=self.provider_name
            )

        try:
            return response.json()
        except ValueError as error:
            raise ProviderError(
                f"{self.provider_name} returned a body that is not JSON: {response.text[:200]}"
            ) from error


def _message_to_wire(message: Message) -> dict[str, Any]:
    wire: dict[str, Any] = {"role": message.role.value, "content": message.content}
    if message.name:
        wire["name"] = message.name
    if message.tool_call_id:
        wire["tool_call_id"] = message.tool_call_id
    if message.tool_calls:
        wire["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
            }
            for call in message.tool_calls
        ]
    if message.role is Role.ASSISTANT and message.tool_calls and not message.content:
        # An assistant turn that only asked for tools has no text; the API wants
        # the key present anyway.
        wire["content"] = None
    return wire


def _tool_to_wire(tool: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.json_schema or {"type": "object", "properties": {}},
        },
    }


def _tool_call_from_wire(raw: dict[str, Any]) -> ToolCallRequest:
    function = raw.get("function") or {}
    raw_arguments = function.get("arguments") or "{}"
    try:
        arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
    except json.JSONDecodeError:
        # Models do emit malformed argument JSON. Surface it as data rather than
        # failing the whole response: the executor can ask the model to retry.
        log.warning("llm.tool_call.invalid_arguments", tool=function.get("name"))
        arguments = {"__raw": raw_arguments}
    return ToolCallRequest(
        id=raw.get("id", ""), name=function.get("name", ""), arguments=arguments
    )
