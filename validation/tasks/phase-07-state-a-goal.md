# Phase 7 validation - stating a goal instead of naming an employee

**Capability under test:** the product becoming itself. Until this phase a user
picked an employee and gave it a task. Now they say what they want, and KAI
works out what that means, who should do it, and whether what came back is
actually what was asked for.

The Definition of Done is a sentence about the user: *one phrase in, a verified
result out, without ever addressing an employee directly.* So none of the
requests below names one, and which employee did what is read back afterwards
as evidence.

## How it was run

`gpt-oss:20b` for comprehension, planning and the work; `lfm2.5:8b` for the
verifications - both on this machine, so the phase is validated without a
provider key and without spending anything.

```bash
export KAI_MODEL_CATALOG_PATH=infrastructure/llm/models.local.toml
uv run alembic upgrade head            # 005 -> 006: objectives, plans, edges
uv run kai ask-kai "<what you want>"   # or: uv run kai serve, and type it
```

The workspace held one file, `meeting-notes.md`, with four people saying one
thing each.

## Result - passed, 2026-09-06

### 1. From a sentence to a file, through a manager

> Read meeting-notes.md in my workspace and write decisions.md listing what each
> person said, one line each.

KAI read the request into two acceptance criteria, planned **one** task -
correctly, since one task was all it needed - chose an employee from the
registry, and had it done. The employee read the file and wrote `decisions.md`.
KAI then checked the result against its own criteria and wrote the answer.

`decisions.md`, first run:

```
Ada: the SQLite migration is finished. One file, no server, no install step.
Bo: the browser extra adds 300 MB. It has to stay optional.
Cy: approvals block on stdin today. That must move into the interface.
Dee: we still have no way to give KAI a goal instead of naming an employee.
```

Nobody named an employee at any point. The record afterwards says who did:

```sql
select assigned_by, json_extract(context, '$.data.granted_tools') from task_assignments;
KAI|["browser.extract","browser.open","computer.click", ... ,"fs.read","fs.write","web.search"]
```

`assigned_by = KAI`, and the granted tools are exactly that employee's own -
which is the whole of what delegation is allowed to hand down.

### 2. The same thing from the interface, watched live

> Count how many people spoke in meeting-notes.md and write the number into
> speakers.txt.

Typed into the page, not the terminal. The stream carries the manager and its
employee as one story - KAI's own lines stamped with the objective, the
employee's stamped only with its task:

```
STAGE  [objective]  Working out what you are asking for.
PLAN   [objective]  Use a single task that reads the meeting notes, counts unique
                    speakers, and writes the numeric result to speakers.txt.
STAGE  [objective]  operator: Read meeting-notes.md, count the number of unique
                    speakers, and write that numeric count to speakers.txt.
STAGE  [task]       Starting: Read meeting-notes.md, count ...
PLAN   [task]       The task requires only reading a local file, extracting
                    speaker names, counting unique entries, and writing ...
```

DONE. `speakers.txt` contains `4`. The criteria KAI held it to were its own,
written before the work started:

```
Number of lines in speakers.txt equals count of speakers in meeting-notes.md
speakers.txt contains only the numeric count
```

45 model calls across all the runs, 94,032 prompt tokens, 7,612 output tokens,
$0.00.

### 3. What the validation found

Three things, all of them from running it rather than from reading it.

**A plan's edges pointed at tasks that had no rows.** The first objective that
decomposed into two tasks failed on a foreign key: `plan_task_dependencies`
keyed its task columns to `tasks`, but KAI records a plan when it *proposes* it,
and a task becomes a row when somebody is given it. The keys were the bug, not
the ordering - a plan that can only be recorded after it has been carried out is
not a plan. Migration 006 keys the edges to `plans` and says why.

**A verdict said "passed" and then listed what was missing.** Read one way that
is a pass; read the other it is not. It is now read the safe way - the list is
the more specific claim, and the one a second attempt can act on - with a
`kai.verdict_contradicted` line so the disagreement is visible rather than
resolved silently. Words that mean "nothing" (`none`, `n/a`) are filtered first,
because a model writing those is agreeing with itself.

**An objective with no acceptance criteria was passing by default.** That made
KAI's own check a no-op exactly when comprehension had been weakest. It now
judges against the request itself - the same fallback the employee verifier
already uses when there is no plan.

## What this does not prove

**Decomposition is only as good as the model doing it.** Asked *"What does WAL
mode change about concurrency in SQLite?"* - a question KAI can answer from what
it knows, and the case §7.5 exists for - `gpt-oss:20b` decided it needed work,
split it into two tasks, searched the web, and invented a constraint nobody
asked for ("20 bullet points"). The direct-answer path is implemented and
covered by tests; a 20B model does not reliably take it. The same goes for the
choice of employee: it picked one that had the right tools but not the closest
role.

**Two model-quality problems the platform does not fix.** The acceptance
criteria a weak reader produces are sometimes steps rather than criteria ("Need
to read meeting-notes.md first"), and the same task run twice produced
`decisions.md` with the speakers' names once and without them the next. The
platform records what was asked, what was decided and what came back; it does
not make a small model consistent.

**Nothing here needed more than one employee at once.** Dependencies between
tasks are declared, checked for cycles, and run in order - but they run one
after another. Concurrency is Phase 12, and the plan shape is what it needs.

**An interrupted objective is not resumed.** A task is (`kai resume`, since
Phase 1), and an objective is fully recorded at every stage - but nothing picks
a half-finished plan back up after a restart. That belongs with the scheduler.
