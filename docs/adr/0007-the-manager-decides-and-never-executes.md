# ADR 0007 - The manager decides and never executes, and the workforce is a directory

**Status:** accepted (Phase 7)

## Context

Phase 7 puts KAI in front of the workforce: the user states an outcome and the
manager works out what that means, who does it, and whether the result is what
was asked for. The plan lists fourteen tasks for it (§7.1-§7.14) and three
governance rules it must not break (§7.13). Underneath those is one question
that decides the shape of everything else: **what is KAI allowed to touch?**

The tempting answer is "everything, it is the manager". That produces a class
that imports the runtime to run a task, the registry to find an employee, the
approval service to unblock one, and - within a phase or two - a branch on an
employee's name. Every guarantee the phases below established would then have a
second path around it.

## Decision

### KAI holds contracts, not components

`application/kai/` imports `domain/` and nothing else. Three contracts carry it:

* `EmployeeRegistry` - the only way it learns who exists;
* `TaskExecution` - one method, `start(task, assignment)`, the only way work
  happens;
* `ObjectiveRepository` / `PlanRepository` - the only way anything is written.

`TaskExecution` is new in this phase and is why the whole manager can be tested
against a stand-in that never calls a model. It takes a task that *already
exists*, because the manager composes the task and picks the employee: handing
over a goal and a name would mean the executor created the task, and a plan's
dependency edges would then point at ids nobody had yet.

`tests/unit/test_kai_governance.py` enforces this by reading `employees/` and
failing if any declared name appears anywhere in `application/kai/` - prose
included, because a name in a comment is a name that will be in a branch later.
It also fails on an import of the runtime, which the layering contract would
otherwise allow.

### Delegation narrows and can never widen

`SharedContext.data["granted_tools"]` records what the manager meant to allow.
The runtime intersects it with the employee's declaration, so:

* KAI can hand down **less** than an employee is trusted with - useful, and now
  possible for the first time;
* KAI cannot hand down **more**, whatever it writes in the assignment, because
  an intersection only ever shrinks.

`effective_tools` in `domain/policies/models.py` has stated this since Phase 1
and had no caller until now. The manager's own actor is the union of the
declared employees' tools - deliberately not a wildcard, which would make the
intersection an identity function and the guarantee vacuous.

### KAI asks for approvals and never answers one

An irreversible action inside a delegated task stops at the same gate it would
have stopped at had the user given the task to that employee directly. The
manager can explain what an action is for; a person says yes. This is enforced
the same way as the rule above: no approval machinery is importable from
`application/kai/`, and the test says so.

### Comprehension and delegation are decisions, so they are stages

Five model-facing components, each routed for what it is: reading the request
and decomposing it get a good model, choosing from a short list of cards gets a
cheap one, the answer the user reads gets a good one again. Two of them exist
because of what they are allowed to *decide against*:

**Not everything needs the workforce.** A request that can be answered outright
gets an answer, not a plan (§7.5). Decomposition is a means; an objective broken
into one task whose whole content is the question already asked has spent an
employee run to restate it.

**The acceptance criteria are written before the work.** They come out of
reading the request, are stored on the objective, and are what the result is
judged against at the end - so the standard cannot be invented after seeing what
was produced. Where the reading produced none, the request itself is the
standard; passing by default there would switch the check off exactly when
comprehension had been weakest.

### A plan is a proposal, and revisions supersede

Replanning writes a new plan at the next revision and marks the previous one
SUPERSEDED rather than editing it. What KAI thought the first time is the only
evidence of why a second attempt was needed. One objective is worth two plans:
the second is told what the first missed, and a third would be told the same
thing again.

Dependencies are declared edges, not an order somebody wrote them in. Edges can
be checked for a cycle - a plan that can never become ready is a bad
decomposition, reported as one rather than looped on - and they say which tasks
could run at the same time, which is what Phase 12 needs and what a list loses.

**The edges carry no foreign key to `tasks`.** A plan is recorded when it is
proposed and a task becomes a row when somebody is given it, so the edges
legally precede both ends they point at. Keying them to `tasks` would mean a
plan could only be recorded after it had already been carried out. (This is not
a theory: it is how the constraint was found.)

### Recovery is chosen from the kind of failure

Retry, reassign, replan - never interchangeable, and never chosen from the text
of a message:

| What the run says | What it means | What happens |
|---|---|---|
| a transient provider error | the outside world blinked | retry, same employee |
| a tool the employee may not use | it could not reach what the task needed | reassign |
| a budget stopped it | more of the same runs out in the same place | replan |
| a person cancelled it | not a failure to recover from | stop |

A retry is a **new task** hanging off the one that failed, not the old one
restarted: a row that says FAILED and later says COMPLETED has lost the first
attempt.

## Consequences

* **Adding an employee is still one directory.** KAI picks it up on the next
  run, and the governance test proves no code names it.
* **The manager can be exercised with no model and no runtime**, which is what
  every test in `tests/unit/test_kai_*` does.
* **`run-task` still exists.** Naming an employee is now the exception - a
  script, a machine with no browser, a phase being validated - rather than the
  way the product is used.
* **Delegation quality is model quality.** The platform records what was asked,
  what was decided, who did it and what came back; it does not make a small
  model choose well. See `validation/tasks/phase-07-state-a-goal.md` for two
  places where a 20B model chose badly and the trace showed exactly why.
* **An objective is not resumable.** Its tasks are, and every stage is recorded,
  but nothing picks a half-finished plan back up after a restart.
