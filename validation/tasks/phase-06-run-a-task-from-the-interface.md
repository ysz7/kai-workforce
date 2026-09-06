# Phase 6 validation - a task run, watched, approved and stopped from the interface

**Capability under test:** the surface the platform is actually used through.
Phase 6's Definition of Done is a sentence about a person, not about a test
suite: *a developer uses KAI without reading logs in a terminal.* So the
validation is four things done from the interface and nowhere else - start a
task, watch it work, answer the question it stops on, and stop one that should
not finish.

## How it was run

Against `gpt-oss:20b` on this machine, so the phase could be validated without a
provider key. One command, one process:

```bash
export KAI_MODEL_CATALOG_PATH=infrastructure/llm/models.local.toml
uv run alembic upgrade head
uv run kai serve            # http://127.0.0.1:8765
```

The workspace held one file, `notes.md`, with three lines of meeting notes.

## Result - passed, 2026-09-06

### 1. A task started and finished from the page

> Read notes.md in the workspace and write a file summary.md containing one line
> per person naming who said what.

COMPLETED in 4 steps. Three tool calls, all at the API level of the hierarchy:
`fs.list`, `fs.read`, `fs.write`. `summary.md` on disk afterwards held exactly
the three lines, one per person.

### 2. The trace, as it happened

The stream carried the run line by line while it ran - not a status column
polled once a step, and nothing that needed a log open beside it:

```
STAGE        Assigned to organizer.
STAGE        Planning the work.
PLAN         The task requires only reading the source file, extracting speaker
             statements, and writing a new file. Three concrete actions suffice.
TOOL_CALL #1 fs.list(path='.', pattern='', recursive=False)
OBSERVATION  fs.list returned: {'entries': [{'path': 'notes.md', ...}], 'count': 1}
TOOL_CALL #2 fs.read(path='notes.md', offset=0)
OBSERVATION  fs.read returned: {'content': '# Meeting notes, 3 March\nAda: ...'}
TOOL_CALL #3 fs.write(path='summary.md', content='Ada: ...')
OBSERVATION  fs.write returned: {'bytes_written': 177, 'overwritten': False}
STAGE        Checking the result against the goal.
RESULT       summary.md created. The file contains: ...
```

Task, step, employee, tool, arguments and the result of the step - 6.3 in full,
and the same words the model saw, because the observation shown is the
observation that went back into the transcript.

### 3. An irreversible action parked on a person, and a click released it

> Overwrite summary.md in the workspace so that it contains exactly the single
> line: Nothing was decided.

`fs.write` on an existing file assessed HIGH, and the run **stopped** - which is
the thing Phase 4 could not do:

```json
{"id": "93ab1411-...", "task_id": "aa36ef64-...", "live": true,
 "action": "fs.write(content='Nothing was decided.', path='summary.md')",
 "risk": "HIGH", "reason": "Overwrite the existing file summary.md"}
```

While it waited, `summary.md` still held the old three lines. Approving it in
the interface returned `{"state": "APPROVED", "live": true}`, the parked tool
call resumed, the task completed, and the file then read `Nothing was decided.`

This closes the gap the Phase 4 validation recorded under *What this does not
prove*: "nothing yet parks a task on it and resumes when the answer arrives.
That belongs with the interface in Phase 6."

### 4. A run stopped while it was working

> Read notes.md, then read summary.md, then read notes.md again, and keep
> re-reading both files in turn to be certain of their contents.

Left to itself this ends at the step limit. Stopped from the interface after
three tool calls, it went to CANCELLED with those three calls still recorded and
its partial result kept. A second task, stopped earlier, was cancelled with zero
calls - between the start of execution and the first call - and reached the same
terminal state. Neither was verified: a deliberate stop is not a failed
verification, and reporting it as one would be a lie about who stopped it.

### 5. History

```
CANCELLED   3 steps  Read notes.md, then read summary.md, then read notes.md again...
CANCELLED   0 steps  List the workspace, then read every file in it one at a time...
COMPLETED   4 steps  Overwrite summary.md in the workspace so that it contains...
COMPLETED   4 steps  Read notes.md in the workspace and write a file summary.md...
```

Four runs, newest first, each one openable afterwards with its plan, its stored
tool calls, its status transitions and its result. 19 model calls, 16,059 prompt
tokens, 1,373 output tokens, $0.00 - shown in the interface, not looked up.

## What this does not prove

**One person, one machine, one process.** The interface binds to loopback and
has no authentication, and that is not an omission to be fixed later by adding a
login - it is the reason the design is safe. Anything that changes the reach of
this surface changes that argument (ADR 0006).

**A closed page is a rejection, not a queue.** An approval parks on a future
inside the running process. That is what makes the run resume the instant the
button is pressed, and it is also why a question nobody answers times out to a
refusal and a killed process leaves a PENDING row nothing is waiting on. The
interface says which of the two a row is (`live`). Durable, answer-it-tomorrow
approvals are a policy question, and belong with the policy engine in Phase 10.

**Cancellation is cooperative.** A task stops between steps or before a tool
call, so a run inside a slow tool keeps going until that tool returns. Killing
it mid-call would leave the outside world in whatever state the tool had reached
and the task row describing a step that never finished - which is precisely the
failure `resume` exists to prevent.

**The trace is not the audit trail.** What the page shows live is a short
in-memory buffer that dies with the process. What happened is still the task
row and the `tool_calls` table, and opening a past run reads those.
