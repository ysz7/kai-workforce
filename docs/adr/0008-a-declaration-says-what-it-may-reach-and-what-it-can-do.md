# ADR 0008 - A declaration says what it may reach and, separately, what it can do

**Status:** accepted (Phase 8)

## Context

Phase 8 asks for three things that turn out to be one: specialised employees
(§8.1), capability discovery in the registry (§8.3), and validation of a
declaration when it loads (§8.2). All three run into the same question, which
the plan's `EmployeeDefinition` does not answer: **what does an employee's
declaration say it can do?**

Until this phase the only capability-shaped field was `model_profile.
capabilities`, and `find_by_capability` matched against it. That is the wrong
field, and wrong in a way that hides: an employee that sorts files needs no more
of a *model* than one that does not. What makes it able to sort them is
`fs.move`. Matching on the model profile makes every employee look alike to a
search, which is exactly when a search stops being worth doing.

Two answers were available.

**Derive it from the tools.** Every `ToolSpec` already declares its
capabilities, so an employee's could be the union of its tools'. Nothing to
write, nothing to keep in step. But the registry reads YAML and knows nothing
about tools; it would have to be handed a tool catalog to load a file, and which
tools exist differs by machine and by flag. An employee would then *be* a
different employee on a machine with the browser extra uninstalled.

**Declare it.** One more list in the file, which can be wrong.

## Decision

### Two lists, because there are two questions

```yaml
allowed_tools: [fs.read, code.run]   # may it?   least privilege
capabilities: [CODE, FILE_ACCESS]    # can it?   what KAI searches by
```

`allowed_tools` is a permission and is enforced: a tool nobody lists is a tool
nobody can call. `capabilities` is an advertisement and is routed on: KAI narrows
the field by it before choosing, so a capability left out is work that never
arrives, and one claimed with no tool behind it is work that arrives and cannot
be started.

Keeping them separate is what lets each be checked against the other. A single
list would have to mean both, and would silently mean the wrong one half the
time - it would either grant a tool by claiming a capability, or hide an
employee that holds the tool but was not written up as offering the category.

Declared rather than derived, so the registry stays a reader of declarations and
an employee is the same employee on every machine. The cost - that a declaration
can lie - is paid by the next section.

### Validation, and the difference between an error and a warning

Nothing in a wrong declaration fails loudly. The tool is never offered to the
model, the capability search never finds the employee, and the run produces a
worse answer for a reason nobody can see in the trace. That is the failure mode
worth a check of its own, and it comes in two kinds - separated not by severity
but by **who can fix it**:

* an **error** is a contradiction inside the declaration: it claims a capability
  nothing it holds provides, *and* everything it holds is present to check. No
  configuration makes that true.
* a **warning** is a mismatch with this machine: a tool that is switched off
  here, or a capability its tools give it that it does not advertise.

The second clause of the error rule took a test to find. An employee holding a
tool this machine does not offer cannot be convicted of claiming too much - the
missing tool may be exactly what backed the claim. That case is already reported
as a missing tool, and reporting it a second time as a fault of the declaration
would be wrong rather than merely noisy.

`domain/employees/validation.py` is given the tools as data, so it runs anywhere
the two are known: the container at start-up (logged, never raised - a workforce
of four with one bad declaration should run the other three), `kai employees`,
and a test that checks the shipped declarations against the shipped tools.

Structural validity is separate and *is* raised, at load, naming the file: an
unknown field, a temperature outside 0-2, a budget of zero, a goal with no text.
`allowed_tool` is not a stricter employee; it is an employee with no tools, and
finding that out at run time means finding it out from a bad answer.

### The directory is the employee's identity

`employees/<name>/` must contain a declaration whose `name` matches it. The
Definition of Done is phrased in terms of that path, `git diff` reads by it, and
a person looking for an employee looks for the directory. It also makes two
employees with one name impossible, which was previously a runtime check.

## Consequences

* **Routing costs nothing when the field narrows to one.** A task that needs
  CODE goes to the only employee that declares it without a model call. The
  validation run picked exactly that path, and the trace says why: *"the only
  employee that declares CODE, FILE_ACCESS"*.
* **A requirement nobody declares is discarded, not obeyed.** It is usually a
  missing declaration rather than a missing employee, and a task routed
  imperfectly beats one routed nowhere. It is logged as `kai.no_one_declares`.
* **Adding an employee is still one directory**, and now includes advertising
  what it is for. `tests/e2e/test_a_new_employee.py` declares one in a temporary
  directory and has KAI find, choose and run it.
* **`capabilities` is a promise the platform does not enforce.** An employee
  claiming FILE_ACCESS with `fs.read` can be given work needing `fs.write`, and
  will fail at the gate like anything else. The check catches the claim that
  nothing at all backs; it does not model what each piece of work will require.
