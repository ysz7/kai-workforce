"""One rule decides whether an action needs a human: how risky it is.

The temptation is a list of special cases - writes outside the working
directory, deletes, sends, payments. That list is unmaintainable, because every
new tool has to remember to add itself to it, and the one that forgets is the
one that does damage.

So risk is a property of the tool, declared in its `ToolSpec`, and a tool that
can tell the difference between a harmless call and a damaging one refines it
per call through `RiskAssessor`. Creating a new file is LOW; overwriting one
that exists is HIGH. Above the threshold, a human decides.

The full `PolicyEngine` with roles and audit arrives in Phase 10. This is
deliberately the smallest thing that makes an irreversible action impossible
without a human - not a governance layer for a single user.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from domain.policies.models import Decision, PolicyDecision, RiskLevel
from domain.tools.models import ToolSpec

#: At and above this level, an action waits for a person.
APPROVAL_THRESHOLD = RiskLevel.HIGH

_ORDER = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.CRITICAL: 3,
}


def at_least(level: RiskLevel, threshold: RiskLevel) -> bool:
    return _ORDER[level] >= _ORDER[threshold]


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    """What a tool says about one specific call it was asked to make."""

    risk_level: RiskLevel
    reason: str = ""


def assess_call(spec: ToolSpec, assessment: RiskAssessment | None = None) -> PolicyDecision:
    """Decide whether this call may proceed or has to wait for a person.

    A tool declared irreversible always waits, whatever it says about the
    individual call - that is what declaring it irreversible means. A reversible
    tool's own assessment of the call wins over its static level, in both
    directions: it knows more about this call than its spec does.
    """
    if spec.reversible:
        level = assessment.risk_level if assessment else spec.risk_level
    else:
        level = _max(spec.risk_level, APPROVAL_THRESHOLD)
        if assessment is not None:
            level = _max(level, assessment.risk_level)

    reason = assessment.reason if assessment else ""
    if at_least(level, APPROVAL_THRESHOLD):
        return PolicyDecision(
            decision=Decision.REQUIRE_APPROVAL,
            reason=reason or f"{spec.name} is a {level.value.lower()}-risk action",
            risk_level=level,
        )
    return PolicyDecision(decision=Decision.ALLOW, reason=reason, risk_level=level)


def _max(left: RiskLevel, right: RiskLevel) -> RiskLevel:
    return left if _ORDER[left] >= _ORDER[right] else right


def describe(spec: ToolSpec, input_data: dict[str, Any], *, width: int = 120) -> str:
    """The one line a person reads before deciding.

    Arguments are trimmed: a confirmation prompt that scrolls a file's contents
    off the screen is a prompt nobody reads before answering.
    """
    parts = []
    for key, value in sorted(input_data.items()):
        rendered = repr(value)
        if len(rendered) > width:
            rendered = rendered[:width] + "..."
        parts.append(f"{key}={rendered}")
    return f"{spec.name}({', '.join(parts)})"
