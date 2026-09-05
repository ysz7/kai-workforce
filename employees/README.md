# Employees

An employee is a **declaration**, not code. Adding `KAI Legal` or
`KAI Recruiter` means adding a definition file here - and nothing in
`application/`, `infrastructure/` or KAI itself may need to change for it.

All employees share one runtime (`application/employee_runtime/`). They differ
only in role, goals, allowed tools, policies, model profile and memory scope.

`infrastructure/employees/yaml_registry.py` discovers them: drop a directory in
here with an `employee.yaml` (and optionally `prompts/system.md`) and
`kai employees` lists it.

`allowed_tools` is least privilege - an employee gets what it lists and nothing
else, and `kai tools` shows the resulting grants per tool. The two shipped
declarations differ only in what they say here: `researcher` searches and reads
pages, `organizer` sorts files. Neither has a line of Python behind it.
