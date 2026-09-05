# ADR 0005 - The interface hierarchy is a property of the tool, and the surface decides the risk

**Status:** accepted (Phase 5)

## Context

Phase 5 gives the platform hands that can reach anything: pixels. Two questions
arrive with it, and the plan states both as requirements (§5.6, §5.8) without
saying where they live.

**Which way in should be used.** An API call is exact, cheap and verifiable; a
click on a picture of a button is a guess about a rendering that may have moved.
Computer Use is what makes the platform able to do anything at all, and that is
precisely why it has to be the last thing tried. The plan asks for "an explicit
implementation of the hierarchy API -> integration -> browser -> Computer Use ->
desktop, with the choice logged and visible in the trace".

**Who has to approve a click.** Phase 4 settled that an action at HIGH risk waits
for a person (ADR 0004). Applying that unchanged to Computer Use gives one of two
useless answers: every click asks - and an employee that asks forty times to fill
in a form is not an employee - or no click asks, and the platform can quietly
empty a mailbox.

## Decision

### The hierarchy is declared on the tool

`ToolSpec.interface_level` names the rung, defaulting to `API`. `fs.*` and
`web.search` are API; `browser.*` is BROWSER; the screen tools are COMPUTER_USE
on the page surface and DESKTOP on the machine.

The alternative was a sentence in a prompt telling the model to prefer the
direct route. That is unenforceable and, worse, invisible: nothing afterwards
can say which rung a run actually used. Declared on the tool, three things
follow for free.

- The choice is made from what the employee **has**, not from what it was told
  about: `select()` reads `list_specs` for that employee.
- The choice is **recorded** - logged as `interface.selected` before the first
  step, written into every `Observation`, and stored on `tool_calls.interface`,
  so a trace read months later still answers "why did it click instead of
  calling something".
- Turning a rung off is a **configuration change** that leaves the rungs below
  it working, because they are different tools. That is Phase 5's Definition of
  Done, and it is checked as one assertion pair in
  `tests/e2e/test_computer_use.py`.

### The two surfaces are two different tools

`computer.*` drives the page the platform opened. `desktop.*` drives the user's
machine. Same code, different names, granted separately in an employee's
`allowed_tools`.

Naming them alike would have been tidier and is wrong: an employee that may
click inside a tab it opened must not thereby be able to click anywhere on the
machine, and least privilege only works if the two can be listed apart.

### The surface decides the risk of the click

`computer.click` is MEDIUM and proceeds. `desktop.click` is irreversible, so it
is HIGH and waits for a person - every time.

This is the deliberate first cut and it is heavier than it will stay. The right
unit of approval for the desktop is the **session**, not the click: a user who
has said "yes, operate Preview for this task" should not be asked again per
action. That needs an interface where answering costs a keystroke rather than a
terminal prompt, which is Phase 6, and a policy engine that can express a
standing grant, which is Phase 10. Until then, per-action approval is the
answer that cannot do damage, and the desktop is off by a flag besides.

The reversible/irreversible line is drawn at the surface rather than the verb
because that is where the difference actually is. A click in a page the platform
opened is undone by going back. A click on the user's desktop can be anything.

### The bounds are a decorator, not a check inside each surface

`GuardedComputer` wraps any `Computer` and enforces the allow-list of
applications, the allowed region of the screen, the action budget and the stop
signal. Nothing else is ever handed out, so there is no path around it - the
same argument as `ApprovalGate` sitting on the single path every tool call takes.

Two of its defaults are worth stating because they are refusals:

- An **empty application allow-list means the desktop is off limits entirely.**
  Acting on the machine is opt-in per application, the way the filesystem tools
  are opt-in per directory.
- **"I could not tell which application is in front" is a refusal**, not a
  shrug. An unanswered question about where a keystroke is about to land is not
  the same as a reassuring answer.

### The stop word is a file

`kai stop` writes `~/.kai-workforce/STOP`, and every action on a screen reads it
first. Not a signal to a process: the run may be busy, may have the screen, and
the terminal that started it may be gone. A file works from a second terminal,
survives the process it stops, and is how Phase 6's interface will pull the same
brake. Its contents are the reason, and the reason is shown to the employee -
"stop, wrong window" tells it something that a bare halt does not.

An unreadable stop file counts as engaged. The alternative is deciding that an
I/O error means "carry on clicking".

## Consequences

- A new tool that drives a screen must declare its rung, or it is treated as a
  direct call and reported as one. The default is the safe one for what a new
  tool usually is; the cost is that a screen tool which forgets is mis-labelled
  in the trace rather than mis-gated.
- Per-action desktop approval will be revisited in Phase 6. Until it is, the
  desktop surface is usable for short scripted work and painful for long work,
  which is the correct way round for a capability this new.
- `tool_calls` gained a column (migration 005). The level is stored rather than
  derived, so a trace does not silently change meaning when a tool is
  re-declared.
