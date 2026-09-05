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
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import structlog

from application.employee_runtime.transcript import Transcript
from domain.capabilities.models import CapabilityRequirement
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
from domain.tasks.plan import Observation, TaskPlan
from domain.tasks.task import Task
from domain.tools.models import ToolResult
from domain.tools.protocols import ToolRegistry

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
        # Injected so tests can control time instead of waiting for it.
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._llm = llm
        self._tools = tools
        self._limits = limits or ExecutionLimits()
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
                result = await self._invoke(call, definition)
                observation = self._observe(transcript.steps, call, result)
                transcript = transcript.with_observation(observation).with_message(
                    Message.tool(observation.summary, call.id)
                )

            if on_step is not None:
                await on_step(transcript)

    # --- Acting ---------------------------------------------------------------

    async def _invoke(
        self, call: ToolCallRequest, definition: EmployeeDefinition
    ) -> ToolResult:
        try:
            tool = self._tools.get(call.name, definition)
        except (ToolNotFoundError, PermissionDeniedError) as error:
            # Not a crash: the model asked for something it cannot have, and
            # being told so is information it can act on.
            log.info("tool.refused", tool=call.name, employee=definition.name, reason=str(error))
            return ToolResult.failure(str(error))

        try:
            return await tool.execute(call.arguments)
        except Exception as error:  # a tool must not take the task down with it
            log.warning("tool.failed", tool=call.name, error=str(error))
            return ToolResult.failure(f"{type(error).__name__}: {error}")

    # --- Observing ------------------------------------------------------------

    def _observe(self, step: int, call: ToolCallRequest, result: ToolResult) -> Observation:
        """Interpret what just happened, explicitly, before deciding anything."""
        if not result.success:
            summary = f"{call.name} failed: {result.error}"
        elif not result.output:
            summary = f"{call.name} returned nothing."
        else:
            summary = f"{call.name} returned: {result.output}"

        observation = Observation(
            step=step,
            summary=summary,
            succeeded=result.success,
            details={"tool": call.name, "arguments": call.arguments},
        )
        log.info(
            "task.observed", step=step, tool=call.name, succeeded=result.success
        )
        return observation

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
    ) -> tuple[Message, ...]:
        """The transcript a fresh run starts from."""
        system = system_prompt or f"You are a {definition.role.title}."
        if definition.goals:
            system += "\n\nYour standing goals:\n" + "\n".join(
                f"- {goal.text}" for goal in definition.goals
            )

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
