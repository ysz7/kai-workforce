# Phase 5 validation - doing something that has no API and no DOM

**Capability under test:** an employee that operates an interface built for a
person. Looks before it acts, acts on a coordinate it was given rather than one
it guessed, and establishes from the screen itself that the action worked.

The employee is `operator`, added in this phase as one YAML file and one prompt -
no Python, no registration, nothing in `application/` or `infrastructure/`
touched.

## The task

A keypad rendered entirely onto a `<canvas>`: enter the code and press OK. This
is the shape of interface the phase exists for - a bank's PIN pad, an embedded
viewer, a control that only answers to a mouse. The DOM has one element and no
text at all, which the run establishes for itself rather than being told:

```
uv run kai run-task --employee operator "Open file:///tmp/kai-phase5/ws/keypad.html
  with browser.open and then read it with browser.extract. Report exactly what
  browser.extract returned."

  -> {'url': '...keypad.html', 'title': 'Secure Keypad', 'text': '', 'characters': 0}
```

The rung above the screen returns an empty string. That is the premise, and it
is a measurement rather than an assertion.

## How it was run

Two local models, so the phase could be validated without a provider key and
without spending anything: `gpt-oss:20b` drives the loop, `qwen2.5vl:7b` looks
at the screen. Nothing in the task, the employee or the runtime names either -
the router is asked for `VISION` and answers from the catalog.

```bash
ollama pull gpt-oss:20b && ollama pull qwen2.5vl:7b
export KAI_MODEL_CATALOG_PATH=infrastructure/llm/models.local.toml
export KAI_WORKSPACE_DIR=/tmp/kai-phase5/ws
uv run alembic upgrade head
uv run kai run-task --employee operator \
  "Open file:///tmp/kai-phase5/ws/keypad.html and enter the code 4 7 2 on the keypad,
   then press OK. The page is a canvas: browser.extract returns nothing, so you must
   work from the screen. Look up each key's coordinates with computer.screen before
   clicking it, and confirm at the end that the screen shows ACCEPTED."
```

## Result - passed, 2026-09-05

Completed in 19 steps, cost $0.00. Every step is a row in `tool_calls` with the
level of the hierarchy it went through:

```
browser.open    BROWSER        opened the page
computer.screen COMPUTER_USE   "Where is the '4' key?"  -> (420, 360)
computer.click  COMPUTER_USE   (420, 360)   verified: true
computer.screen COMPUTER_USE   "Where is the '7' key?"  -> (448, 496)
computer.click  COMPUTER_USE   (448, 496)   verified: true
computer.screen COMPUTER_USE   "Where is the '2' key?"  -> (608, 232)
computer.click  COMPUTER_USE   (608, 232)   verified: true
computer.screen COMPUTER_USE   "Where is the 'OK' button?" -> (812, 594)
computer.click  COMPUTER_USE   (812, 594)   verified: true  -> "ACCEPTED"
```

### Checked independently, not taken on the model's word

A vision model saying "the screen shows ACCEPTED" is exactly what a vision model
that cannot see would also say. So the four coordinates it chose were replayed
against the page afterwards and the page's own state read out of it:

```
PAGE STATE: ['472', 'ACCEPTED']
```

Every coordinate lands inside the key it was asked for - `4` spans x 360-540 and
y 280-390, and it clicked (420, 360) - and the string that reached the page is
the one that was asked for. The page's own JavaScript decided `ACCEPTED`, which
it does only for `472`.

### The Definition of Done: the flag, and what survives it

```
$ kai tools                                # computer use off, the default
computer.click  MEDIUM  COMPUTER_USE  operator
...

$ KAI_FLAGS__COMPUTER_USE=true kai tools   # and on
desktop.click   HIGH    DESKTOP       nobody  [needs approval]
desktop.screen  LOW     DESKTOP       nobody
...
```

The desktop is absent until the flag turns it on, and when it appears every
action that changes state on it is marked as waiting for a person - while
looking and scrolling are not, because a prompt about nothing is how people
learn to click through the prompts that matter.

Turning a rung off leaves the rungs below it working, because they are different
tools rather than one tool with a switch: the `browser.extract` run quoted at
the top of this page completed with computer use off, and the file and search
tools were untouched throughout. `tests/e2e/test_computer_use.py` holds the same
claim as an assertion.

## What went wrong, and why it is recorded here

**The vision model under-reported once.** After the first click on OK the check
came back `verified: false` - it described the keypad and missed the green
ACCEPTED. The employee looked again and clicked OK a second time, which
re-evaluated the same code and confirmed. Two steps wasted, nothing broken.

The direction of that error is the one the design chose: `ScreenReader.confirm`
treats an unreadable or uncertain answer as a **no**, so the failure mode is a
run that checks twice rather than one that reports success it never saw.

**A hallucinated target on the first, vague question.** Asked "what does the
screen show?", the model returned a target labelled *Save button* - there is no
Save button on this page. The employee did not click it; its next question was
specific, and the specific questions were all answered correctly. A general
question about a screen gets a general answer, and general answers are where
invented coordinates come from.

**A malformed tool call, handled as Phase 4 intended.** Step 10 sent
`{"x": 448, "coord?": "??"}` with no `y`. The call came back with the shape it
should have had, and the next step was correct - the behaviour
`validation/tasks/phase-04-research-from-the-web.md` describes, still holding
with a second model in the loop.

## What this does not prove

**The desktop surface was not driven.** The validation ran on the browser
surface, which is where the blast radius is one tab. `DesktopComputer` is
covered by tests against a fake driver and by the constraint suite, but no run
recorded here moved the real mouse. That belongs with a task someone actually
wants done on their machine.

**Coordinates from a 7B model are not reliable in general.** They were right
here because the targets are 180x110 pixels. A dense toolbar is a different
problem, and the honest answer for one today is a better vision model - which is
a line in `models.toml`, not a change to any of this.

**A screen operated is not a screen understood.** The gate stops the run from
claiming an unverified success; it does not stop the model from confirming the
wrong thing convincingly. That is what `computer.verify` narrows and does not
close.
