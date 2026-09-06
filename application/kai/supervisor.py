"""Running a plan, and deciding what a failed task means.

The employee runtime already retries inside a task: a rejected verdict sends the
work back through planning once. This is the layer above, and it answers a
different question - not "should this task try again" but "does the objective
still have a route to done, and what is it".

Three answers, and they are not interchangeable (§7.7):

* **retry** - the same task, the same employee, because the failure was
  transient and the second attempt has as good a chance as the first;
* **reassign** - the same task, somebody else, because the employee could not
  reach what the task needed;
* **replan** - a different decomposition, because the task itself was wrong.

Retrying a task that nobody can do, or reassigning one that failed because the
provider was down, both burn a budget to arrive back where they started. So the
choice is made from the *kind* of failure, by type and by what the run reported,
never by the text of a message - the same rule `application/orchestrator.py`
follows one layer down.

Dependencies are honoured, and a task whose dependency failed is never started:
a summary written from a source that was never fetched is worse than no summary.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from uuid import UUID

import structlog

from application.kai.delegation import CapabilityDelegator
from domain.capabilities.models import CapabilityRequirement
from domain.policies.models import ActorKind
from domain.tasks.progress import NullProgress, ProgressEvent, ProgressKind, ProgressSink
from domain.tasks.task import Task, TaskStatus
from domain.workforce.assignment import SharedContext, TaskAssignment
from domain.workforce.protocols import Plan, PlanProgress, TaskExecution

log = structlog.get_logger(__name__)

#: How many times one task is put back to work before the plan is reconsidered.
#: Two, because the runtime has already retried once inside the task: a third
#: outer attempt is the fifth model conversation about the same instruction.
MAX_TASK_ATTEMPTS = 2


class Recovery(StrEnum):
    RETRY = "RETRY"
    REASSIGN = "REASSIGN"
    REPLAN = "REPLAN"
    GIVE_UP = "GIVE_UP"


@dataclass(frozen=True, slots=True)
class TaskOutcome:
    """One finished task, and who did it."""

    task: Task
    employee: str
    reason: str = ""

    @property
    def succeeded(self) -> bool:
        return self.task.status is TaskStatus.COMPLETED


@dataclass(frozen=True, slots=True)
class Supervision:
    """What became of a plan."""

    plan: Plan
    outcomes: tuple[TaskOutcome, ...]
    recovery: Recovery | None = None
    #: Why the plan stopped short, in the words the replanner will be given.
    shortfall: tuple[str, ...] = ()

    @property
    def progress(self) -> PlanProgress:
        completed = sum(1 for outcome in self.outcomes if outcome.succeeded)
        return PlanProgress(
            plan_id=self.plan.id,
            total=len(self.plan.tasks),
            completed=completed,
            failed=len(self.outcomes) - completed,
            running=0,
        )

    @property
    def all_succeeded(self) -> bool:
        return len(self.outcomes) == len(self.plan.tasks) and all(
            outcome.succeeded for outcome in self.outcomes
        )

    @property
    def cost_usd(self) -> float:
        return sum(outcome.task.cost_usd for outcome in self.outcomes)


def classify(task: Task) -> Recovery:
    """What a finished-but-not-completed task calls for next.

    Read from the run, not from prose: whether a budget stopped it, whether a
    tool was refused, whether verification rejected it. A task that was stopped
    by a person is not a failure to recover from at all.
    """
    if task.status is TaskStatus.COMPLETED:
        return Recovery.RETRY  # never consulted; kept total for the caller's sake
    if task.status is TaskStatus.CANCELLED:
        return Recovery.GIVE_UP

    stopped_by = (task.result.output.get("stopped_by") if task.result else None) or None
    if stopped_by:
        # It ran out of budget rather than out of ideas. More of the same, from
        # the same employee, would run out again at the same place.
        return Recovery.REPLAN

    kind = task.error.kind if task.error else ""
    if kind in _TRANSIENT_ERRORS:
        return Recovery.RETRY
    if kind == "PermissionDeniedError" or _was_refused_a_tool(task):
        # The employee could not reach what the task needed. Somebody else may.
        return Recovery.REASSIGN
    return Recovery.REPLAN


#: Failures where the same attempt is worth making again. Named by type, because
#: a message is not a contract and a retry decision made from one is a guess.
_TRANSIENT_ERRORS = frozenset(
    {"RateLimitError", "ProviderTimeoutError", "ProviderError", "ProviderUnavailableError"}
)


def _was_refused_a_tool(task: Task) -> bool:
    observations = (task.result.output.get("observations") if task.result else None) or ()
    return any(
        isinstance(item, dict)
        and not item.get("succeeded", True)
        and "may not use" in str(item.get("summary", ""))
        for item in observations
    )


class Supervisor:
    """Carries a plan to the end, or to the point where it cannot go on."""

    def __init__(
        self,
        *,
        execution: TaskExecution,
        delegator: CapabilityDelegator,
        progress: ProgressSink | None = None,
        max_attempts: int = MAX_TASK_ATTEMPTS,
    ) -> None:
        self._execution = execution
        self._delegator = delegator
        self._progress = progress or NullProgress()
        self._max_attempts = max_attempts

    async def run(
        self, plan: Plan, *, context: SharedContext | None = None, objective_id: UUID | None = None
    ) -> Supervision:
        """Run every task whose dependencies are met, until none are left."""
        done: set[UUID] = set()
        outcomes: list[TaskOutcome] = []
        shortfall: list[str] = []
        recovery: Recovery | None = None
        carried = context or SharedContext()

        while True:
            ready = plan.ready(done)
            if not ready:
                break
            for planned in ready:
                outcome = await self._carry(
                    planned, carried, objective_id, plan.requirements.get(planned.id)
                )
                outcomes.append(outcome)
                if outcome.succeeded:
                    done.add(planned.id)
                    carried = _carry_forward(carried, outcome)
                    continue

                # A failed task stops the plan: whatever depended on it would be
                # working from a result that does not exist.
                recovery = classify(outcome.task)
                shortfall.append(
                    f"{planned.goal} - {outcome.reason or 'did not complete'}"
                )
                log.info(
                    "kai.task_failed",
                    task_id=str(planned.id),
                    employee=outcome.employee,
                    status=outcome.task.status.value,
                    recovery=recovery.value,
                )
                break
            if recovery is not None:
                break

        if recovery is None and plan.blocked(done):
            # Nothing failed and nothing is ready: the edges describe a cycle,
            # which is a bad decomposition rather than a bad run.
            recovery = Recovery.REPLAN
            shortfall.append(
                "The plan's dependencies cannot all be satisfied; some tasks never became ready."
            )

        return Supervision(
            plan=plan,
            outcomes=tuple(outcomes),
            recovery=recovery,
            shortfall=tuple(shortfall),
        )

    # --- One task -------------------------------------------------------------

    async def _carry(
        self,
        planned: Task,
        context: SharedContext,
        objective_id: UUID | None,
        requirement: CapabilityRequirement | None = None,
    ) -> TaskOutcome:
        """Give one task to somebody, and try again if that is what the failure wants."""
        attempt = 1
        avoid: set[str] = set()
        outcome = await self._attempt(planned, context, objective_id, avoid, requirement)

        while not outcome.succeeded and attempt < self._max_attempts:
            recovery = classify(outcome.task)
            if recovery is Recovery.REASSIGN:
                # Do not hand it back to the employee that could not reach it.
                avoid.add(outcome.employee)
            elif recovery is not Recovery.RETRY:
                break
            attempt += 1
            log.info(
                "kai.task_reattempt",
                task_id=str(planned.id),
                attempt=attempt,
                recovery=recovery.value,
            )
            # A second attempt is a new task, not the old one restarted: the
            # first is already in a terminal state, and a row that says FAILED
            # and later says COMPLETED is a row that lost the first attempt.
            outcome = await self._attempt(
                _next_attempt(planned, attempt), context, objective_id, avoid, requirement
            )

        return outcome

    async def _attempt(
        self,
        planned: Task,
        context: SharedContext,
        objective_id: UUID | None,
        avoid: set[str],
        requirement: CapabilityRequirement | None = None,
    ) -> TaskOutcome:
        # `DelegationError` is deliberately not caught here. It means the machine
        # has no declared employee at all - a fact about the workforce, not
        # about this task - and every replanned attempt would end in the same
        # place. It belongs to whoever owns the objective.
        chosen, passed, why = await self._delegator.choose(
            planned, context=context, avoid=avoid, requirement=requirement
        )

        await self._announce(
            planned,
            objective_id,
            f"{chosen.name}: {planned.goal}",
            payload={"employee": chosen.name, "why": why, "task_id": str(planned.id)},
        )

        assignment = TaskAssignment.create(
            task_id=planned.id,
            employee_id=chosen.id,
            assigned_by=ActorKind.KAI,
            assigned_by_id="kai",
            context=passed,
            workspace_id=planned.workspace_id,
        )
        finished = await self._execution.start(
            replace(planned, assigned_employee_id=chosen.id), assignment
        )
        return TaskOutcome(task=finished, employee=chosen.name, reason=_why(finished))

    async def _announce(
        self,
        task: Task,
        objective_id: UUID | None,
        message: str,
        *,
        payload: dict[str, object] | None = None,
    ) -> None:
        try:
            await self._progress.emit(
                ProgressEvent(
                    task_id=task.id,
                    kind=ProgressKind.STAGE,
                    message=message,
                    objective_id=objective_id,
                    payload=dict(payload or {}),
                    workspace_id=task.workspace_id,
                )
            )
        except Exception as error:  # a watcher must not be able to fail a run
            log.warning("progress.emit_failed", error=str(error))


def _next_attempt(planned: Task, attempt: int) -> Task:
    """The same goal, as a fresh task hanging off the one that failed.

    Kept as a child rather than a sibling so the history reads as what it was -
    one piece of work, attempted twice - and so `tasks.parent_id` answers "what
    was this a retry of" without a join through the plan.
    """
    return replace(
        Task.create(
            planned.goal,
            workspace_id=planned.workspace_id,
            created_by=planned.created_by,
            priority=planned.priority,
            parent_id=planned.id,
        ),
        plan_id=planned.plan_id,
        attempts=attempt - 1,
    )


def _why(task: Task) -> str:
    if task.status is TaskStatus.COMPLETED:
        return ""
    if task.error:
        return f"{task.error.kind}: {task.error.message}"
    return f"ended {task.status.value.lower()}"


def _carry_forward(context: SharedContext, outcome: TaskOutcome) -> SharedContext:
    """What a finished task hands to the ones that depend on it.

    A summary and the files it named, not the transcript. The next employee is
    being told what is now true, which is a decision the manager makes - not
    handed a log to read.
    """
    summary = outcome.task.result.summary.strip() if outcome.task.result else ""
    if not summary:
        return context
    artifacts = outcome.task.result.artifacts if outcome.task.result else ()
    return SharedContext(
        facts=(*context.facts, f"{outcome.task.goal} -> {summary}"),
        constraints=context.constraints,
        artifacts=(*context.artifacts, *artifacts),
        data=context.data,
    )
