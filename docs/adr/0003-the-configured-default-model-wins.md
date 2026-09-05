# ADR 0003 - The configured default model wins over routing hints

**Status:** accepted (Phase 2)

## Context

`ModelRouter.select` takes a `CapabilityRequirement` and `RoutingHints`
(quality, latency, cost, context, tools). `models.toml` also names a default
model per task kind.

A first implementation scored every candidate - quality, minus estimated cost
weighted by `cost_sensitivity`, plus a small bonus for the configured default.
It failed its own test: with ordinary hints, a higher-quality model outscored
the configured default and got chosen instead. Editing `models.toml` would then
not reliably change which model runs, which is exactly the phase's stated DoD.

## Decision

Precedence is explicit and ordered:

1. **Requirements filter.** A model that lacks a required capability or context
   window is never a candidate.
2. **The configured default wins** if it survives that filter.
3. **Hints rank the remainder**, and only when the task kind has no default or
   the default cannot do the work.

A caller that genuinely needs something else expresses it as a requirement -
`Capability.VISION`, a minimum context - which filters at step 1.

`RoutingHints.needs_tools` is folded into the requirement rather than treated as
a preference: routing to a model that cannot call tools fails at run time.

## Consequences

- Changing models is editing `models.toml`, with no caller to hunt down.
- Model choice is predictable and its reason is reported (`ModelChoice.reason`),
  which matters when the surprise is a bill.
- Hints are weaker than their name suggests. That is the trade: a soft
  preference is not allowed to silently pick a more expensive model.
