# ADR 0002 - Domain values stay dataclasses; Pydantic guards the edges

**Status:** accepted (Phase 2)

## Context

The plan lists `LLMRequest / LLMResponse / Message / Usage / ToolCall` as
"(Pydantic)", and the stack table names Pydantic v2 for validation and DTOs.

Phase 1 built the rest of the domain - `Task`, `EmployeeDefinition`,
`TaskAssignment`, `MemoryItem` - as frozen dataclasses, and pinned that with a
linter contract: `domain/` depends on nothing.

Making only the LLM values Pydantic would leave two kinds of value object in one
layer, with different construction, mutation and equality rules, and the seam
between them running straight through the employee runtime.

## Decision

Domain values are frozen dataclasses, uniformly. Pydantic is used where data
actually arrives from outside and has to be checked:

- `app/config/settings.py` - environment and `.env` (pydantic-settings);
- provider payloads, validated at the adapter boundary in `infrastructure/llm/`.

## Consequences

- One shape of value object across `domain/`, and the zero-dependency contract
  stays literally true.
- Validation happens where untrusted data enters, which is the boundary the
  plan's intent points at: an `LLMResponse` built inside the process was already
  checked when it was parsed.
- A malformed provider body raises `ProviderError` from the adapter rather than
  a `ValidationError` from a domain type - the error taxonomy stays intact.
- If DTOs ever cross a process boundary (an HTTP API in Phase 6), the request and
  response models for it are Pydantic and live in `app/ui/`, not in `domain/`.
