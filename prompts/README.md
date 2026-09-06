# Prompts

Versioned prompt templates, loaded by `application/prompts.py` from
`prompts/<name>/<version>.md`. One location and one loader: a prompt that lived
beside its component would be the same file under a second convention.

`planner`, `verifier` and `screen_reader` belong to an employee run. The `kai_*`
templates are the manager's: reading a request, decomposing it, choosing who
does what, judging the result and writing the one answer the user reads.

Prompts are written in English. The language an agent answers the user in is the
`KAI_RESPONSE_LANGUAGE` setting, never text hard-coded here.
