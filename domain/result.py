"""A minimal Result type for outcomes that are expected to fail routinely.

Exceptions stay the mechanism for bugs and broken invariants. `Result` is for
outcomes a caller is meant to branch on - a tool call that failed, a policy that
denied an action - where raising would turn ordinary control flow into
exception handling.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn, TypeGuard


@dataclass(frozen=True, slots=True)
class Ok[T]:
    value: T

    @property
    def is_ok(self) -> bool:
        return True

    def unwrap(self) -> T:
        return self.value


@dataclass(frozen=True, slots=True)
class Err[E]:
    error: E

    @property
    def is_ok(self) -> bool:
        return False

    def unwrap(self) -> NoReturn:
        raise ValueError(f"Cannot unwrap an error result: {self.error}")


type Result[T, E] = Ok[T] | Err[E]


def is_ok[T, E](result: Result[T, E]) -> TypeGuard[Ok[T]]:
    return isinstance(result, Ok)
