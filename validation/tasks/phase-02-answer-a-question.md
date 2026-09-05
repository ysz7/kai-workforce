# Phase 2 validation - answer a question through a real model

**Capability under test:** the platform can reach a model, get a real answer,
and report what the call cost.

## How it was run

Against a local model, so the phase could be validated with no provider key and
no spend. The bundled local catalog does this:

```bash
export KAI_MODEL_CATALOG_PATH=infrastructure/llm/models.local.toml
uv run alembic upgrade head
uv run kai ask "Which city is the capital of Germany? Answer in one short sentence."
uv run kai spend
```

## Result - passed, 2026-09-05

```
{"task_kind": "CONVERSATION", "model": "gpt-oss:20b",
 "reason": "configured default for conversation", "event": "llm.routed"}
{"provider": "local", "model": "gpt-oss:20b", "prompt_tokens": 81,
 "output_tokens": 51, "cost_usd": 0.0, "latency_ms": 7420, "event": "llm.call"}

Berlin is the capital of Germany.

[gpt-oss:20b] 81 in / 51 out - $0.000000 - 7420 ms
```

`kai spend` then reported `calls: 1`, `prompt tokens: 81`, `output tokens: 51`,
confirming the call was recorded rather than only displayed.

Tool calling was verified against the same model in
`tests/integration/test_local_provider.py`: the model asked for `get_weather`
with `{"city": "Berlin"}`, and the replayed exchange - assistant turn carrying
the tool call, then a tool-result message - was accepted and used
("The current weather in Berlin is 14 °C with rain").

## What a local model does not prove

Cost accounting is exercised at zero, which is the true price of a local call
but not a test of arithmetic against a real bill - that is covered by unit tests
with a priced catalog. Rate-limit handling has no local equivalent either; it is
covered by `tests/unit/test_retry.py`. Running the same question against a
hosted provider remains worth doing once a key exists, but the capability this
phase claims is demonstrated.
