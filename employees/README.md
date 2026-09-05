# Employees

An employee is a **declaration**, not code. Adding `KAI Legal` or
`KAI Recruiter` means adding a definition file here - and nothing in
`application/`, `infrastructure/` or KAI itself may need to change for it.

All employees share one runtime (`application/employee_runtime/`). They differ
only in role, goals, allowed tools, policies, model profile and memory scope.

The registry that loads these declarations arrives in Phase 3.
