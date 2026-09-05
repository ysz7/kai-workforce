# ADR 0004 - Approval is a declared risk level, not a list of dangerous actions

**Status:** accepted (Phase 4)

## Context

The plan describes the Phase 4 approval gate as "a list of irreversible actions
(writing outside the working directory, deleting, sending, paying) requiring
confirmation". Phase 4 gives employees hands - files, a browser, a subprocess -
and the brake has to arrive with them.

A list has one failure mode, and it is the important one: it lives somewhere
other than the tool it governs. Every new tool has to remember to add itself,
and the tool whose author forgets is not the harmless one - it is the one nobody
thought about. The list is also wrong at the granularity it can express.
`fs.write` is not dangerous; `fs.write` onto a file that already exists is.
`fs.move` is not dangerous; sorting forty documents would be unusable if each
move asked a question.

## Decision

Risk is a property of the tool, and the rule is one sentence: **an action at
HIGH or CRITICAL risk waits for a person.**

- `ToolSpec.risk_level` is the tool's static level, declared next to what the
  tool does.
- `ToolSpec.reversible = False` raises the floor to HIGH and cannot be argued
  down. `code.run` is declared this way.
- A tool that can tell one call from another implements `RiskAssessor.assess`
  and returns a level for *this* call. `fs.write` answers LOW for a new file and
  HIGH for an overwrite; `fs.move` answers LOW for a free destination and HIGH
  for one that would replace a file.
- `ApprovalGate` sits on the single path every tool call takes, between the
  executor and the tool. Not inside the executor, where it would be checked once
  and forgotten by the next tool; not inside each tool, where it would be
  re-implemented per tool and omitted by one.

Writing outside the working directory is deliberately *not* on this list.
`Workspace.resolve` refuses it outright, after resolving symlinks. A
confirmation prompt for something that cannot happen teaches the user to click
through prompts.

## Consequences

- A new tool declares its own risk in the same file as its behaviour. There is
  no register to update and no way to be omitted from one.
- With no approver configured, or nobody at the terminal, the answer is no. An
  unattended run cannot consent by being silent.
- The gate has no notion of *who* may approve what, no roles, and no audit trail
  beyond the `approvals` table. That is Phase 10's `PolicyEngine`, and this is
  deliberately the smallest thing that makes an irreversible action impossible
  without a human.
- A rejected action is refused immediately rather than parked as a question to
  answer later. The PENDING row and `kai approve <id>` exist; nothing yet
  suspends a task on one. That waits for the interface in Phase 6.
