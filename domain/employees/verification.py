"""Verification is explicit. Success is never assumed.

A model reporting that it finished is evidence, not proof - it is the same model
that would report finishing if it had hallucinated the whole thing. So the
result is checked against the goal before a task is allowed to complete.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Verdict:
    passed: bool
    reason: str = ""
    #: What the verifier found missing. Fed back into a retry so the second
    #: attempt is better informed than the first, rather than merely repeated.
    missing: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def ok(cls, reason: str = "") -> Verdict:
        return cls(passed=True, reason=reason)

    @classmethod
    def rejected(cls, reason: str, *missing: str) -> Verdict:
        return cls(passed=False, reason=reason, missing=tuple(missing))
