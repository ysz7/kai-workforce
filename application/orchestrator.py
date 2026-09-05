"""The task lifecycle, and what to do when it goes wrong.

The runtime knows how to do the work. This knows what a failure means: whether
to try again, whether to give up, and what to write down either way. Keeping
that apart matters because the two answer to different things - the runtime to
the employee's declaration, this to the shape of the failure.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import structlog

from domain.errors import (
    ConfigurationError,
    ExecutionError,
    KaiError,
    PermissionDeniedError,
    ProviderError,
    StorageError,
)

log = structlog.get_logger(__name__)


class FailureKind(StrEnum):
    """Why a task failed, in the only terms that change what happens next."""

    #: The outside world was briefly unavailable. Trying again is reasonable.
    TRANSIENT = "TRANSIENT"
    #: The request was wrong, or not allowed. Trying again changes nothing.
    PERMANENT = "PERMANENT"
    #: The platform is misconfigured. A human has to fix it.
    CONFIGURATION = "CONFIGURATION"
    #: The work itself did not succeed - no plan, no result, budget spent.
    EXECUTION = "EXECUTION"
    #: Something we did not anticipate. Treated as permanent, and logged loudly.
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class Failure:
    kind: FailureKind
    error_type: str
    message: str

    @property
    def is_retryable(self) -> bool:
        return self.kind is FailureKind.TRANSIENT


def classify(error: BaseException) -> Failure:
    """Map an exception onto what should happen next.

    Retrying is a decision about the *kind* of failure, never about the text of
    a message, so this reads types and the provider's own `transient` flag.
    """
    name = type(error).__name__
    message = str(error)

    if isinstance(error, ProviderError):
        kind = FailureKind.TRANSIENT if error.transient else FailureKind.PERMANENT
    elif isinstance(error, ConfigurationError):
        kind = FailureKind.CONFIGURATION
    elif isinstance(error, PermissionDeniedError):
        kind = FailureKind.PERMANENT
    elif isinstance(error, StorageError):
        # The local database being unreadable is not something a retry fixes.
        kind = FailureKind.CONFIGURATION
    elif isinstance(error, ExecutionError):
        kind = FailureKind.EXECUTION
    elif isinstance(error, KaiError):
        # Every deliberate error of ours that is not one of the above: a broken
        # rule, a missing entity, a bad request. None of them improve on a retry.
        kind = FailureKind.PERMANENT
    else:
        kind = FailureKind.UNKNOWN
        log.error("task.unexpected_error", error_type=name, error=message)

    return Failure(kind=kind, error_type=name, message=message)
