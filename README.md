# KAI Workforce

A **local-first** platform where an AI manager runs digital employees that do
real work on your own machine.

```
User -> KAI (AI Manager) -> Workforce -> Digital Employees -> Capabilities -> External World
```

No server, no cluster, no account. You clone the repository, add a provider key,
and give KAI a task.

## Status

**Phase 4 - Capability / Tool Layer.** Employees do things now: read and sort
files inside one working directory, search the web, open a page and read it, run
a short program under limits. Anything irreversible - overwriting a file,
running generated code - waits for you to say yes. Phase 5 adds Computer Use.

See `dev-assets/implementation-plan.md` for the full roadmap.

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

## Giving an employee a task

```bash
uv run kai employees           # who is declared
uv run kai tools               # what this machine can do, and who may do it
uv run kai run-task --employee researcher "Explain what SQLite WAL mode changes about concurrency, with sources."
uv run kai resume              # pick up anything that was interrupted
```

Every task goes through three stages. **Plan** turns the goal into steps.
**Execute** runs a tool-calling loop bounded by three budgets at once - steps,
cost and wall time - and each action is followed by an explicit observation
rather than feeding raw output into the next decision. **Verify** judges the
result against the goal, and a task cannot complete without passing; a rejected
result goes back through planning once, told what was missing.

State is written to the task after every step, so `kill -9` mid-run loses
nothing: `kai resume` continues from the last saved step instead of starting
over.

## Tools, and the brake on them

An employee gets the tools its declaration lists and nothing else - `kai tools`
prints the grants, so least privilege is something you can read rather than
trust. The filesystem tools see one directory (`KAI_WORKSPACE_DIR`, by default
`~/.kai-workforce/workspace`) and refuse any path that resolves outside it,
symlinks followed.

An action at HIGH or CRITICAL risk waits for a person. Overwriting a file that
exists is HIGH; creating a new one is not. Running generated code always is.
With nobody at the terminal the answer is no, so an unattended run cannot
consent by being silent - set `KAI_APPROVAL_MODE=allow` if that is what you
want on your own machine. See [ADR 0004](docs/adr/0004-approval-is-a-risk-level-not-a-list-of-actions.md).

```bash
uv run kai approvals           # what is waiting on a decision
uv run kai approve <id>        # or: kai reject <id> --comment "not that file"
```

The browser is an optional extra, so installing the platform does not download a
browser engine for a workforce that only reads files:

```bash
uv sync --extra browser && uv run playwright install chromium
```

### Adding a tool

One file under `infrastructure/tools/` and one line in
`infrastructure/tools/builtin.py`. Declare the parameters and the JSON Schema
the model sees is generated from them; declare the risk and the gate applies it.
Nothing in the runtime changes.

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

## Adding an employee

Create `employees/<name>/employee.yaml`. That is the whole change - no class, no
registration, no edit to the runtime:

```yaml
name: analyst
role: Data Analyst
goals:
  - text: Say what the data supports, and no more.
allowed_tools: [fs.read]        # least privilege: it gets what it lists
model_profile:
  capabilities: [TEXT_REASONING, CODE]
limits:
  max_steps: 6
  max_cost_usd: 0.25
```

An optional `prompts/system.md` next to it gives the employee its own voice.
All employees share one runtime; a second runtime would mean the difference
between two employees had stopped being declarative.

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
| `prompts/` | Content | Planner and verifier templates, versioned as files. |

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
