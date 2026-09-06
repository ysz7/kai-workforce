# Employees

An employee is a **declaration**, not code. Adding `KAI Legal` or
`KAI Recruiter` means adding a directory here - and nothing in `application/`,
`infrastructure/` or KAI itself may need to change for it.

All employees share one runtime (`application/employee_runtime/`). They differ
only in role, goals, allowed tools, declared capabilities, policies, model
profile and memory scope.

```
employees/<name>/
    employee.yaml          the whole employee
    prompts/system.md      optional: its own voice
```

The directory name is the employee's identity, and `employee.yaml` must declare
the same `name`. `infrastructure/employees/yaml_registry.py` discovers it, and
refuses a declaration it cannot make sense of - an unknown field, a temperature
outside 0-2, a budget of zero - naming the file that caused it. A typo fails at
load rather than becoming an employee with no tools.

## The two lists, and what each is for

`allowed_tools` is **least privilege**: an employee gets what it lists and
nothing else, and `kai tools` shows the resulting grants per tool. A tool nobody
lists is a tool nobody can call.

`capabilities` is **discovery**: what kind of work this employee can be given.
KAI searches by these, so a capability left out is work that never arrives, and
one claimed with no tool behind it is work that arrives and cannot be started.
`kai employees` prints both, and says which declarations disagree with the tools
this machine actually has.

The distinction matters because the two answer different questions - *may it?*
and *can it?* - and a single list would silently answer one of them wrong.

## The four that ship

| | does | reaches the world through |
|---|---|---|
| `researcher` | finds out what is true and says where it came from | web, browser, files |
| `organizer` | puts a folder of documents in order | files |
| `operator` | works interfaces that have no API and no usable DOM | browser, then the screen |
| `analyst` | computes answers from data on this machine | files, and code it runs |

Four, not thirty. Each is one file plus a prompt, and none of them has a line of
Python behind it - `tests/e2e/test_a_new_employee.py` proves that by declaring a
fifth in a temporary directory and having KAI use it.
