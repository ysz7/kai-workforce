# ADR 0001 - Configuration is passed into the container, not read by it

**Status:** accepted (Phase 1)

## Context

The implementation plan places `Settings` in `app/config/settings.py` and the DI
`Container` in `infrastructure/container.py`. It also states the import rule:

```
app             -> application, domain
application     -> domain
infrastructure  -> domain
domain          -> (nothing)
```

Taken literally these two are in conflict: a container that calls
`get_settings()` makes `infrastructure` import `app`, which the linter rejects -
and rightly, because it would let any adapter reach up into the interface layer.

## Decision

`Container` receives its configuration rather than fetching it. It declares what
it needs as `infrastructure/settings.py::RuntimeSettings`, a Protocol; the
composition root in `app/config/container.py` builds the container from the real
`Settings`.

The composition root is therefore in `app/`, and `app` is allowed to import
`infrastructure` - that is what a composition root is for. Everything below it
keeps the plan's rule exactly.

## Consequences

- The layering contract passes as written, enforced by `import-linter` and by
  `tests/unit/test_architecture_boundaries.py`.
- Tests build a container from any object satisfying `RuntimeSettings` without
  touching environment variables.
- `alembic/env.py` still reads `Settings` directly. It is a standalone script
  and a composition root of its own, not part of the `infrastructure` package.
