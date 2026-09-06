"""Error taxonomy shared by every layer.

Domain code raises these; infrastructure adapters are responsible for mapping
vendor-specific failures onto them, so nothing above `infrastructure/` ever has
to know which provider failed.
"""

from __future__ import annotations


class KaiError(Exception):
    """Base class for every error the platform raises on purpose."""


# --- Configuration and wiring -------------------------------------------------


class ConfigurationError(KaiError):
    """The platform is misconfigured and cannot start or serve a request."""


class DependencyNotConfiguredError(ConfigurationError):
    """A dependency was requested from the container before it was available."""


# --- Domain rules -------------------------------------------------------------


class DomainError(KaiError):
    """A domain rule was violated."""


class InvalidStateTransitionError(DomainError):
    """A task was asked to move to a status it cannot reach from the current one."""

    def __init__(self, from_status: str, to_status: str) -> None:
        super().__init__(f"Invalid task transition: {from_status} -> {to_status}")
        self.from_status = from_status
        self.to_status = to_status


class NotFoundError(DomainError):
    """A referenced entity does not exist."""


class TaskNotFoundError(NotFoundError):
    def __init__(self, task_id: object) -> None:
        super().__init__(f"Unknown task: {task_id}")


class EmployeeNotFoundError(NotFoundError):
    def __init__(self, name: str) -> None:
        super().__init__(f"Unknown employee: {name}")


class ToolNotFoundError(NotFoundError):
    def __init__(self, name: str) -> None:
        super().__init__(f"Unknown tool: {name}")


class ToolInputError(DomainError):
    """A tool was called with arguments it cannot work with.

    Reported back to the model rather than raised at the user: being told the
    argument was wrong is something a model can act on in the next step.
    """


class SecretNotFoundError(ConfigurationError):
    """A tool asked for a credential that is not configured on this machine."""


# --- Permissions --------------------------------------------------------------


class PermissionDeniedError(DomainError):
    """An actor tried to use a capability it is not allowed to use.

    Delegation never escalates privileges: effective rights are the intersection
    of the delegating actor's rights and the executing actor's rights.
    """


class ApprovalRequiredError(DomainError):
    """An irreversible action was attempted without a human decision."""


class ApprovalDeniedError(DomainError):
    """A human was asked about an irreversible action and said no."""


# --- Execution ----------------------------------------------------------------


class ExecutionError(KaiError):
    """A task could not be carried out."""


class LimitExceededError(ExecutionError):
    """A run hit one of its budgets: steps, cost or wall time."""

    def __init__(self, kind: str, detail: str = "") -> None:
        super().__init__(f"Execution limit reached ({kind}){f': {detail}' if detail else ''}")
        self.kind = kind


class StopRequestedError(ExecutionError):
    """The user pulled the brake while the platform was acting on the machine."""


class ComputerUseError(ExecutionError):
    """An action on a screen could not be carried out."""


class PlanningError(ExecutionError):
    """The model did not produce a usable plan."""


class DelegationError(ExecutionError):
    """There is no one to give this task to.

    A configuration problem wearing an execution problem's clothes - a machine
    with no declared employee cannot do work - but it surfaces mid-objective and
    is answered by adding a declaration, so it is reported to the user with the
    objective it stopped rather than at start-up.
    """


class VerificationFailedError(ExecutionError):
    """The result did not hold up, and no attempts are left."""

    def __init__(self, reason: str, missing: tuple[str, ...] = ()) -> None:
        super().__init__(reason)
        self.missing = missing


# --- Storage ------------------------------------------------------------------


class StorageError(KaiError):
    """The local store could not be read or written."""


class StorageNotInitializedError(StorageError):
    """The database exists but has no schema yet; migrations have not been run."""


# --- External providers -------------------------------------------------------


class ProviderError(KaiError):
    """An external provider failed. Base class for adapter-level failures."""

    transient: bool = False


class RateLimitError(ProviderError):
    transient = True


class TimeoutError(ProviderError):
    transient = True


class InvalidRequestError(ProviderError):
    """The provider rejected the request; retrying the same payload will not help."""


class ProviderUnavailableError(ProviderError):
    transient = True
