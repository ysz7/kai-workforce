# Phase 8 validation - a fourth employee, added as a directory

**Capability under test:** specialisation. Four employees instead of one, each a
declaration; a registry that can be searched by what an employee says it can do;
and a check that catches a declaration saying something untrue.

**Definition of Done:** *`git diff` after adding an employee contains only
`employees/<name>/**`.*

## How it was run

Two ways, because the phase has two claims to answer.

The DoD is a claim about the codebase, and is checked as a test:
`tests/e2e/test_a_new_employee.py` writes a fifth employee into a temporary
directory - one `employee.yaml`, nothing else - and has KAI find it, choose it,
and run it. Nothing is imported, registered or edited for it to work.

The routing is a claim about behaviour, and was run against a real model:
`claude-haiku-4-5` for every stage, through the Anthropic adapter written for
this phase.

```bash
export KAI_MODEL_CATALOG_PATH=infrastructure/llm/models.anthropic.toml
uv run kai employees          # both lists, and what disagrees with this machine
uv run kai ask-kai "<goal>"
```

## Result - passed, 2026-09-06

### 1. The analyst was added as one directory

`employees/analyst/` - a declaration and a prompt. It is the first employee that
can *compute* an answer rather than read one, and the whole of what makes it so
is two lines: `code.run` in `allowed_tools`, `CODE` in `capabilities`.

```
$ kai employees
analyst  Data Analyst
  tools:  code.run, fs.list, fs.read, fs.write
  can do: CODE, FILE_ACCESS
  limits: 16 steps, $1.0, 300s
```

`kai tools` shows the other half of the same fact: the line for `code.run` read
`nobody` before this phase and reads `analyst` after it. That is one declaration,
visible without reading any of them.

### 2. Both routes to an employee, in one run

> Work out the total revenue per region from sales.csv and write the answer into
> revenue.md.

```
kai.delegated  candidates=['analyst']  employee=analyst
               reason='the only employee that declares CODE, FILE_ACCESS'
```

The plan said the task needed `CODE`, the registry answered with one employee,
and **no model call was made to choose** - the field of one was already the
answer. That is what a declared capability buys.

The second objective shows the other route:

> Read meeting-notes.md and write decisions.md with one line per person saying
> what they said.

```
kai.delegated  candidates=['analyst', 'operator', 'organizer', 'researcher']
               employee=analyst
               reason="The task requires reading a file on this machine and
                       extracting its raw content, which is the analyst's core function."
```

Every employee declares `FILE_ACCESS`, so narrowing left all four and the model
chose. Both files came out right: `revenue.md` holds east $431.20, north
$346.04, south $316.44 - checked independently against the CSV - and
`decisions.md` holds one line per person.

83 model calls, 209,950 prompt tokens, 20,827 output tokens, $0.31.

### 3. What running it found

Four things, none of which reading the code would have shown.

**Tool names with a dot are a 400.** Every tool this platform declares is
`fs.read` or `code.run`; the Messages API accepts `^[a-zA-Z0-9_-]{1,128}$`. The
first real objective failed on it. Names are now translated on the way out and
translated *back* on the way in - the name the executor checks permissions
against has to be the name it knows, or the call is refused as a tool the
employee may not use. Two names that would sanitise to the same string are kept
apart rather than merged.

**A dated snapshot was priced at zero.** The API answers with
`claude-haiku-4-5-20251001` where the catalog says `claude-haiku-4-5`, so the
price lookup missed and `kai spend` reported $0.00 for a call that cost money -
against the catalog's own stated rule. The lookup now falls back to the longest
configured name the answer starts with, and will not let a shorter name price a
different model.

**A setting that did nothing.** `KAI_LLM_TIMEOUT_SECONDS` was documented in
`.env.example`, held in `Settings`, and passed to no provider. It reaches them
now, and unset means each provider's own default - two minutes hosted, ten for a
model on this machine - which is a better answer than one number for both.

**The gate stopped generated code, unattended.** Run without a terminal
attached, `code.run` was refused four times: HIGH risk, no approver reachable,
so the answer is no. The analyst then reported figures it had worked out in its
head, and KAI's verifier **refused them** for having no evidence behind them.
Two rules from two earlier phases holding at once, under a real model.

### 4. And a fix that was a declaration, not code

With approvals allowed, the analyst computed the right answer, wrote the file -
and was escalated anyway, because its report described the file instead of
showing it. The verifier was right by its own rule: a criterion with no evidence
is unmet.

The fix was four lines in `employees/analyst/prompts/system.md` telling it to
read back what it wrote and quote it. The next run passed, with the same model
and the same data. That is the phase's thesis in one change: an employee that
was doing the work and failing the check was fixed by editing its own file.

## What this does not prove

**Capability narrowing discriminates; the model's judgement is less reliable.**
Where the plan named `CODE`, routing was exact and free. Where every employee
qualified, `claude-haiku-4-5` sent a "summarise these notes" task to the analyst
- defensible, since it can read files, but `organizer` or `researcher` is the
better fit. Declaring capabilities narrows the field; it does not make a small
model choose well within one.

**`capabilities` is a promise the platform does not fully enforce.** The check
catches a claim nothing at all backs. It does not model what each piece of work
will actually require, so an employee claiming `FILE_ACCESS` with only `fs.read`
can still be handed work that needs `fs.write` and fail at the gate.

**The Anthropic adapter is not exercised in full.** No streaming, no thinking,
no prompt caching, no structured outputs - the platform asks for none of them
yet. The JSON-object response format has no equivalent on this API and is
dropped rather than translated; every caller that sets it also says so in its
prompt and parses the reply forgivingly, which is why that is safe here and
would not be in general.

**Four employees is not a workforce.** Three, then four, is the point: the value
of this phase is that a fifth costs a directory, not that four is enough.
