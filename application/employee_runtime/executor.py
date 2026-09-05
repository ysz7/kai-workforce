"""The work loop: think, act, observe, repeat - inside a budget.

Two things here are deliberate and easy to get wrong.

**Observe is a real step.** A loop that goes straight from a tool result to the
next tool call has nowhere to notice that the result was empty, contradicted the
last one, or already answered the question. So every action is followed by an
explicit interpretation, recorded on the task, and the next decision is made
from that rather than from raw output.

**Limits are checked before each step, not after the run.** An agent that loops
does not fail loudly; it keeps working and keeps spending. Stopping at a budget
is a normal outcome with a normal result, not a crash.

**Every tool call passes the same three checks, in this order:** may this
employee use this tool at all, does this particular call need a human, and what
did it cost. Permission first, because refusing an unknown tool is cheaper than
asking about it; approval second, because a question the user answers is only
worth asking for a call that would otherwise happen.

**The interface hierarchy is decided from what the employee has, and recorded.**
The tools an employee is allowed to use are what say whether it can reach the
world through an API, a browser or a screen, so the choice is made here, once,
from `list_specs` - logged before the first step, stated to the model, and
written against every call. A trace can then answer why a run clicked on a
picture of a button instead of calling something.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace

import structlog

from application.employee_runtime.approvals import ApprovalGate
from application.employee_runtime.transcript import Transcript
from domain.capabilities.models import CapabilityRequirement
from domain.computer.interfaces import InterfaceLevel, describe, select
from domain.employees.definition import EmployeeDefinition
from domain.employees.limits import ExecutionLimits, LimitKind
from domain.errors import PermissionDeniedError, ToolNotFoundError
from domain.llm.models import (
    LLMRequest,
    Message,
    RoutingHints,
    TaskKind,
    ToolCallRequest,
)
from domain.llm.protocols import LLM
from domain.secrets.models import redact
from domain.tasks.plan import Observation, TaskPlan
from domain.tasks.task import Task
from domain.tools.models import ToolResult
from domain.tools.protocols import ToolRegistry
from domain.tools.telemetry import ToolCallLog, ToolCallRecord

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class StepOutcome:
    """One turn of the loop, and whether the work should continue."""

    transcript: Transcript
    finished: bool = False
    answer: str = ""
    stopped_by: LimitKind | None = None


class Executor:
    """Implements `domain.employees.protocols.Executor`."""

    def __init__(
        self,
        llm: LLM,
        tools: ToolRegistry,
        *,
        limits: ExecutionLimits | None = None,
        approvals: ApprovalGate | None = None,
        call_log: ToolCallLog | None = None,
        # Injected so tests can control time instead of waiting for it.
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._llm = llm
        self._tools = tools
        self._limits = limits or ExecutionLimits()
        self._approvals = approvals or ApprovalGate()
        self._call_log = call_log
        self._clock = clock

    async def run(
        self,
        task: Task,
        definition: EmployeeDefinition,
        transcript: Transcript,
        *,
        on_step: Callable[[Transcript], Awaitable[None]] | None = None,
    ) -> StepOutcome:
        """Advance the task until it finishes or runs out of budget.

        `on_step` is awaited after each step with the current transcript. That
        callback is what makes a killed process resumable, so it runs before the
        next model call, not at the end.
        """
        started = self._clock()
        specs = self._tools.list_specs(definition)
        choice = select(spec.interface_level for spec in specs)
        if choice is not None:
            log.info(
                "interface.selected",
                task_id=str(task.id),
                employee=definition.name,
                level=choice.level.value,
                reason=choice.reason,
                available=[level.value for level in choice.available],
            )

        while True:
            exceeded = self._limits.exceeded_by(
                steps=transcript.steps,
                cost_usd=transcript.cost_usd,
                elapsed_seconds=self._clock() - started,
            )
            if exceeded is not None:
                log.warning(
                    "task.limit_reached",
                    task_id=str(task.id),
                    limit=exceeded.value,
                    steps=transcript.steps,
                    cost_usd=round(transcript.cost_usd, 6),
                )
                return StepOutcome(
                    transcript=transcript,
                    finished=True,
                    answer=self._best_answer(transcript),
                    stopped_by=exceeded,
                )

            response = await self._llm.generate(
                LLMRequest(
                    messages=transcript.messages,
                    tools=tuple(specs),
                    temperature=definition.model_profile.temperature,
                )
            )
            transcript = transcript.with_spend(response.usage.cost_usd).advanced()

            if not response.tool_calls:
                transcript = transcript.with_message(Message.assistant(response.content))
                if on_step is not None:
                    await on_step(transcript)
                return StepOutcome(transcript=transcript, finished=True, answer=response.content)

            transcript = transcript.with_message(
                Message.assistant(response.content, tool_calls=response.tool_calls)
            )
            for call in response.tool_calls:
                result = await self._invoke(call, definition, task)
                observation = self._observe(transcript.steps, call, result, definition)
                transcript = transcript.with_observation(observation).with_message(
                    Message.tool(observation.summary, call.id)
                )

            if on_step is not None:
                await on_step(transcript)

    # --- Acting ---------------------------------------------------------------

    async def _invoke(
        self, call: ToolCallRequest, definition: EmployeeDefinition, task: Task
    ) -> ToolResult:
        try:
            tool = self._tools.get(call.name, definition)
        except (ToolNotFoundError, PermissionDeniedError) as error:
            # Not a crash: the model asked for something it cannot have, and
            # being told so is information it can act on.
            log.info("tool.refused", tool=call.name, employee=definition.name, reason=str(error))
            return ToolResult.failure(str(error))

        gate = await self._approvals.check(tool, call.arguments, task, definition)
        if not gate.allowed:
            log.info("tool.not_approved", tool=call.name, task_id=str(task.id))
            await self._record(task, call, ToolResult.failure(gate.reason))
            return ToolResult.failure(gate.reason)

        started = self._clock()
        try:
            result = await tool.execute(call.arguments)
        except Exception as error:  # a tool must not take the task down with it
            log.warning("tool.failed", tool=call.name, error=str(error))
            result = ToolResult.failure(f"{type(error).__name__}: {error}")

        if not result.latency_ms:
            result = replace(result, latency_ms=int((self._clock() - started) * 1000))
        await self._record(task, call, result, tool.spec.interface_level)
        return result

    async def _record(
        self,
        task: Task,
        call: ToolCallRequest,
        result: ToolResult,
        interface: InterfaceLevel = InterfaceLevel.API,
    ) -> None:
        """Account for the call. Never at the cost of the task itself."""
        if self._call_log is None:
            return
        try:
            await self._call_log.record(
                ToolCallRecord(
                    tool=call.name,
                    success=result.success,
                    latency_ms=result.latency_ms,
                    task_id=task.id,
                    input_data=call.arguments,
                    output=result.output,
                    error=result.error,
                    interface=interface,
                )
            )
        except Exception as error:  # telemetry is not worth failing a run over
            log.warning("tool.telemetry_failed", tool=call.name, error=str(error))

    # --- Observing ------------------------------------------------------------

    def _observe(
        self,
        step: int,
        call: ToolCallRequest,
        result: ToolResult,
        definition: EmployeeDefinition,
    ) -> Observation:
        """Interpret what just happened, explicitly, before deciding anything."""
        # Redacted here, not at the log: this summary goes back into the
        # transcript, which is persisted and sent to the model on the next step.
        output = redact(result.output)
        if not result.success:
            summary = f"{call.name} failed: {result.error}"
        elif not output:
            summary = f"{call.name} returned nothing."
        else:
            summary = f"{call.name} returned: {output}"

        interface = self._interface_of(call.name, definition)
        observation = Observation(
            step=step,
            summary=summary,
            succeeded=result.success,
            details={
                "tool": call.name,
                "arguments": redact(call.arguments),
                "interface": interface.value,
            },
        )
        log.info(
            "task.observed",
            step=step,
            tool=call.name,
            interface=interface.value,
            succeeded=result.success,
        )
        return observation

    def _interface_of(self, name: str, definition: EmployeeDefinition) -> InterfaceLevel:
        """How this call reached the world. A refused call reached it not at all."""
        try:
            return self._tools.get(name, definition).spec.interface_level
        except (ToolNotFoundError, PermissionDeniedError):
            return InterfaceLevel.API

    # --- Fallbacks ------------------------------------------------------------

    @staticmethod
    def _best_answer(transcript: Transcript) -> str:
        """What to report when a run is cut short.

        Whatever the employee last said is more useful than an empty result, and
        the caller is told separately that a limit stopped it.
        """
        for message in reversed(transcript.messages):
            if message.content and message.role.value == "assistant":
                return message.content
        return ""

    @staticmethod
    def opening_messages(
        task: Task,
        definition: EmployeeDefinition,
        plan: TaskPlan | None,
        system_prompt: str,
        feedback: tuple[str, ...] = (),
        interfaces: tuple[InterfaceLevel, ...] = (),
    ) -> tuple[Message, ...]:
        """The transcript a fresh run starts from."""
        system = system_prompt or f"You are a {definition.role.title}."
        if definition.goals:
            system += "\n\nYour standing goals:\n" + "\n".join(
                f"- {goal.text}" for goal in definition.goals
            )
        # Told to the model in the same terms the trace records it in, and only
        # when it has a choice to make: an employee with one level has no
        # hierarchy to respect, and a paragraph about one is noise.
        ladder = describe(interfaces)
        if ladder:
            system += f"\n\n{ladder}"

        instruction = f"# Task\n\n{task.goal}"
        if plan and not plan.is_empty:
            instruction += "\n\n# Your plan\n\n" + "\n".join(
                f"{step.index + 1}. {step.description}"
                + (f" (expected: {step.expected_outcome})" if step.expected_outcome else "")
                for step in plan.steps
            )
        if feedback:
            instruction += (
                "\n\n# A previous attempt was rejected\n\nFix these before answering:\n"
                + "\n".join(f"- {item}" for item in feedback)
            )
        instruction += (
            "\n\nWork through this and then give your final answer as plain text. "
            "Call a tool only when you need one."
        )
        return (Message.system(system), Message.user(instruction))

    @staticmethod
    def routing(
        definition: EmployeeDefinition,
    ) -> tuple[TaskKind, CapabilityRequirement, RoutingHints]:
        return (
            TaskKind.EXECUTION,
            definition.model_profile.as_requirement(),
            RoutingHints(
                quality=0.7,
                cost_sensitivity=0.5,
                needs_tools=bool(definition.allowed_tools),
            ),
        )
