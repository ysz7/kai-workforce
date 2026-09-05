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


# --- Permissions --------------------------------------------------------------


class PermissionDeniedError(DomainError):
    """An actor tried to use a capability it is not allowed to use.

    Delegation never escalates privileges: effective rights are the intersection
    of the delegating actor's rights and the executing actor's rights.
    """


class ApprovalRequiredError(DomainError):
    """An irreversible action was attempted without a human decision."""


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
