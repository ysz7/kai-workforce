# Phase 3 validation - a researcher, end to end

**Capability under test:** one digital employee, declared and not coded, takes a
goal through plan -> execute -> verify and produces something a person would
read. And: a task killed mid-run continues rather than restarts.

## How it was run

Against `gpt-oss:20b` on this machine, so the phase could be validated without a
provider key.

```bash
export KAI_MODEL_CATALOG_PATH=infrastructure/llm/models.local.toml
uv run alembic upgrade head
uv run kai run-task --employee researcher \
  "Summarize what SQLite WAL mode changes about concurrent reads and writes, and say where that comes from."
```

## Result - passed, 2026-09-05

The task planned in three steps, executed, was verified, and completed. The
output was a table contrasting rollback-journal and WAL locking, a paragraph of
synthesis, and a source list. `kai spend` recorded three model calls: planning
and execution on `gpt-oss:20b`, verification on `lfm2.5:8b` - each stage routed
by its own task kind, as configured.

### The Definition of Done: kill it and resume

A second run was killed with `kill -9` forty seconds in, during execution. What
was on disk afterwards:

```
status: RUNNING | step: 1
stage: EXECUTING
plan steps: 5 steps, saved
messages: 4 | observations: ['browser.search failed: Unknown tool: browser.search']
```

`uv run kai resume` then made **one** execution call and one verification call
and completed the task at step 2. No `task.planned` event appears in the resume
log: it continued from the saved transcript rather than starting over, and did
not pay for a second plan.

The refused `browser.search` in that transcript is the tool gate working. The
researcher declares no tools; the model reached for one anyway, was told it does
not have it, and carried on - a refusal is information, not a crash.

## What this does not prove

**Sources are only as good as the model.** The 20B local model cited
`sqlite.org/wiki/UsingWAL`, which does not exist. The employee's own prompt
tells it not to invent references and it did anyway. Nothing in Phase 3 can fix
that: an employee with no tools is working from training data, and the fix is
Phase 4 - a browser and a search tool, so claims can be fetched rather than
recalled. Verification catches an empty or self-contradictory answer; it cannot
catch a plausible URL that happens not to exist.

**Resume granularity is the stage, not the token.** With no tools, execution is
one long model call, so a process killed inside that call repeats it. Once tools
arrive, each tool round trip is a saved step, and the granularity gets finer for
free - the machinery is already there, as the observation above shows.
