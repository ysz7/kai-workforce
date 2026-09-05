# KAI Workforce

A **local-first** platform where an AI manager runs digital employees that do
real work on your own machine.

```
User -> KAI (AI Manager) -> Workforce -> Digital Employees -> Capabilities -> External World
```

No server, no cluster, no account. You clone the repository, add a provider key,
and give KAI a task.

## Status

**Phase 2 - LLM Abstraction.** On top of Phase 1's domain, task state machine and
local SQLite store, the platform can now reach a model: a provider-neutral `LLM`
contract, one working adapter, capability-aware routing from a catalog, retry on
transient failures only, and cost accounting on every call. The employee runtime
lands in Phase 3. See `dev-assets/implementation-plan.md` for the full roadmap.

## Getting started

```bash
uv sync
uv run kai --version
uv run alembic upgrade head    # creates ~/.kai-workforce/kai.db
uv run kai config
uv run kai models              # the model catalog and its defaults
```

Copy `.env.example` to `.env` and set `KAI_LLM_API_KEY`, then:

```bash
uv run kai ask "Which city is the capital of Germany?"
uv run kai spend               # what the calls have cost so far
```

### Without a key, and without spending anything

A model running on this machine works just as well, and is what Phase 2 was
validated against:

```bash
ollama serve && ollama pull gpt-oss:20b
export KAI_MODEL_CATALOG_PATH=infrastructure/llm/models.local.toml
uv run kai ask "Which city is the capital of Germany?"
```

That is the same code path - router, adapter, metering, spend log - pointed at a
different catalog. Local calls are priced at zero because they are.

## Changing models

Edit `infrastructure/llm/models.toml`. Nothing in `domain/`, `application/` or an
employee declaration names a model or a vendor, so that file is the whole change.

A caller asks for what the work *needs* - reasoning, tool calling, a long
context - and the router answers from the catalog. Precedence is: requirements
filter the field, the configured default for that kind of work wins, hints rank
whatever is left. See [ADR 0003](docs/adr/0003-the-configured-default-model-wins.md).

## Layout

| Directory | Layer | Rule |
|---|---|---|
| `app/` | Interface | CLI today, a local UI in Phase 6. The composition root lives here. |
| `application/` | Coordination | Orchestration and the one shared employee runtime. Depends on `domain/` only. |
| `domain/` | Business logic | Protocols and values. Depends on nothing. |
| `infrastructure/` | Adapters | Providers, persistence, tools. Depends on `domain/` only. |
| `employees/` | Declarations | An employee is a definition file, not code. |

The import rules are enforced by `import-linter` and by
`tests/unit/test_architecture_boundaries.py`. An `httpx` import inside `domain/`
fails CI.

## Development

```bash
uv run pytest                        # no network, no provider keys needed
uv run ruff check .
uv run lint-imports
uv run python scripts/check_english_only.py
```

`tests/integration/test_local_provider.py` is the one exception to "no network":
it talks to a model on this machine when one is running, and skips itself when
one is not. Nothing in the suite ever needs a key or a paid call.

The codebase is English-only - identifiers, comments, logs, schema and docs. Task
goals, memory contents and report text are runtime data and may be in any
language; the language agents answer in is the `KAI_RESPONSE_LANGUAGE` setting.
