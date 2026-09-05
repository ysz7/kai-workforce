"""The conversation so far, in a form that survives a restart.

Resumability lives or dies here. A run that is killed mid-task has to come back
knowing what it already said, what tools it already called and what came back -
otherwise "resume" means "start again and pay twice".

So the transcript is a value that can be written to the task's `state` column
after every step and read back by a different process.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from domain.llm.models import Message, Role, ToolCallRequest
from domain.tasks.plan import Observation


def message_to_state(message: Message) -> dict[str, Any]:
    state: dict[str, Any] = {"role": message.role.value, "content": message.content}
    if message.name:
        state["name"] = message.name
    if message.tool_call_id:
        state["tool_call_id"] = message.tool_call_id
    if message.tool_calls:
        state["tool_calls"] = [
            {"id": call.id, "name": call.name, "arguments": call.arguments}
            for call in message.tool_calls
        ]
    return state


def message_from_state(raw: dict[str, Any]) -> Message:
    return Message(
        role=Role(raw["role"]),
        content=raw.get("content", ""),
        name=raw.get("name"),
        tool_call_id=raw.get("tool_call_id"),
        tool_calls=tuple(
            ToolCallRequest(
                id=call.get("id", ""),
                name=call.get("name", ""),
                arguments=call.get("arguments", {}),
            )
            for call in raw.get("tool_calls", ())
        ),
    )


@dataclass(frozen=True, slots=True)
class Transcript:
    """Messages, observations and what has been spent, as one resumable value."""

    messages: tuple[Message, ...] = ()
    observations: tuple[Observation, ...] = ()
    cost_usd: float = 0.0
    steps: int = 0

    def with_message(self, *messages: Message) -> Transcript:
        return replace(self, messages=(*self.messages, *messages))

    def with_observation(self, observation: Observation) -> Transcript:
        return replace(self, observations=(*self.observations, observation))

    def with_spend(self, cost_usd: float) -> Transcript:
        return replace(self, cost_usd=self.cost_usd + cost_usd)

    def advanced(self) -> Transcript:
        return replace(self, steps=self.steps + 1)

    @property
    def last_observation(self) -> Observation | None:
        return self.observations[-1] if self.observations else None

    # --- Persistence ----------------------------------------------------------

    def to_state(self) -> dict[str, Any]:
        return {
            "messages": [message_to_state(m) for m in self.messages],
            "observations": [o.to_dict() for o in self.observations],
            "cost_usd": self.cost_usd,
            "steps": self.steps,
        }

    @classmethod
    def from_state(cls, state: dict[str, Any] | None) -> Transcript:
        if not state:
            return cls()
        return cls(
            messages=tuple(message_from_state(m) for m in state.get("messages", ())),
            observations=tuple(
                Observation.from_dict(o) for o in state.get("observations", ())
            ),
            cost_usd=float(state.get("cost_usd", 0.0)),
            steps=int(state.get("steps", 0)),
        )


@dataclass(frozen=True, slots=True)
class RunState:
    """Everything a resumed run needs, including which stage it stopped in."""

    stage: str = "PLANNING"
    transcript: Transcript = field(default_factory=Transcript)
    attempt: int = 1
    verifier_feedback: tuple[str, ...] = ()

    def to_state(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "attempt": self.attempt,
            "verifier_feedback": list(self.verifier_feedback),
            "transcript": self.transcript.to_state(),
        }

    @classmethod
    def from_state(cls, state: dict[str, Any] | None) -> RunState:
        if not state:
            return cls()
        return cls(
            stage=state.get("stage", "PLANNING"),
            transcript=Transcript.from_state(state.get("transcript")),
            attempt=int(state.get("attempt", 1)),
            verifier_feedback=tuple(state.get("verifier_feedback", ())),
        )
