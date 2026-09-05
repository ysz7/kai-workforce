from __future__ import annotations

from typing import Protocol


class Computer(Protocol):
    """The last interface an employee reaches for, and the one that makes the
    platform actually work on a machine rather than talk about it."""

    async def screenshot(self) -> bytes: ...

    async def click(self, x: int, y: int) -> None: ...

    async def type(self, text: str) -> None: ...

    async def press(self, key: str) -> None: ...

    async def scroll(self, amount: int) -> None: ...
