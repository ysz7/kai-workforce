# ADR 0006 - The interface runs inside the process it watches, and the runtime announces itself

**Status:** accepted (Phase 6)

## Context

Phase 6 asks for a local interface with a live execution trace (§6.3), approvals
answered in it (§6.4), and cancellation of a running task (§6.6). The plan says
what it should do and not how any of it is wired, and the obvious shape - a web
server that talks to the platform - turns out to be three separate decisions
wearing one hat.

**Where the work runs.** A server that starts tasks in a worker process is the
familiar arrangement, and it makes every one of the three features expensive: a
trace becomes a message bus, an approval becomes a durable queue with a
correlation id, and cancelling becomes a signal to a process that may be in the
middle of a tool call.

**Where the trace comes from.** The task row is saved after every step and the
tool-call log after every call. Both are written to be read afterwards. Polling
either one gives a page that lags by a step and cannot show a plan, a stage, or a
question - none of which are rows.

**What "stop" means.** There is already a brake: `kai stop` writes a STOP file
that every screen action reads (ADR 0005). It stops the machine, from a second
terminal, immediately. That is the right design for a hand on a mouse and the
wrong one for "this task is not going anywhere, end it and keep what it found".

## Decision

### The interface is the platform, not a client of it

`kai serve` starts one process. The FastAPI app, the container, the employee
runtime and the SQLite file are the same process, and the run of a task is an
`asyncio` task on the same event loop that serves the requests.

Everything Phase 6 asks for follows from that and needs nothing else:

* the trace is an in-memory fan-out, not a broker;
* an approval is a coroutine parked on a `Future`, released by the request that
  answers it - so the run resumes the instant the button is pressed;
* cancelling is a set membership test the loop makes between steps.

It binds to `127.0.0.1` and has no authentication. Those are one decision, not
two: this surface starts tasks, approves irreversible actions and can drive the
machine's screen, and it is safe without a password precisely because nothing
off this machine can reach it. The host is a setting rather than a flag so that
binding it elsewhere is a deliberate edit, and `kai serve` warns when the address
is not loopback.

### Progress is announced by the runtime, not derived from storage

`domain/tasks/progress.py` adds one value (`ProgressEvent`) and one contract
(`ProgressSink`). The runtime and the executor emit; `NullProgress` is the
default, so a run nobody is watching costs nothing to be watchable, and the CLI
is unchanged.

Two properties are load-bearing, both stated as "the watcher is expendable, the
work is not":

* an emit that raises is logged and swallowed - a browser tab cannot fail a run;
* the broadcaster's per-subscriber queue drops when full rather than blocking -
  a stalled connection cannot stall an employee.

The buffer is short and per task. It exists so a page opened mid-run shows the
lines it missed, not so the stream becomes a second audit trail. **What happened
is still the task row and the `tool_calls` table**, which outlive the process;
opening a past run reads those, and reads them the same way for a run from last
week and one that finished a second ago.

A stream watching one task ends when that task does. A finished run has nothing
further to say, and a connection held open on one is a connection the page has
to be taught to ignore.

### Cancelling a task is not the STOP file, and does not become it

Two brakes, because they answer different questions:

| | `kai stop` | cancel a task |
|---|---|---|
| scope | the machine's screen | one task |
| asked by | anyone, from any terminal | the interface running it |
| read | before each physical action | between steps, before each tool call |
| stored | a file under `$KAI_DATA_DIR` | in memory, for this process |
| outcome | actions refused | task CANCELLED, partial result kept |

Cancellation is **cooperative**. A coroutine killed mid-tool leaves the outside
world in whatever state the tool had reached and the task row describing a step
that never finished - exactly the failure `resume` exists to prevent. So the run
stops itself, writes its own terminal state, and keeps what it did.

It is deliberately *not* persisted. The person asking is talking to the process
that is running the task; a file would buy nothing and would then need cleaning
up after a crash. A task cancelled and then interrupted comes back through
`resume` as the task it was, and can be cancelled again.

A cancelled run is not verified. Nobody claimed it had finished, so there is
nothing to check it against, and a rejected verdict would report a deliberate
stop as a failure.

## Consequences

* **A closed page is a refusal, not a queue.** An approval waits on a future in
  this process; nobody answering times out to no, and a killed process leaves a
  PENDING row nothing is parked on. The interface distinguishes the two (`live`).
  Approvals that survive a restart are a policy question and belong to Phase 10.
* **A slow tool delays a cancel.** The check is between steps and before calls,
  never inside one.
* **The runtime gained a dependency it can ignore.** `ProgressSink` and
  `CancellationSignal` both default to a component that does nothing, so nothing
  above them is required to know either exists.
* **FastAPI and uvicorn are core dependencies**, unlike the browser and desktop
  extras. From this phase on the interface is how the platform is used, and a
  surface half the installations cannot open is not the primary surface.
