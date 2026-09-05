from __future__ import annotations

from typing import Protocol

from domain.memory.models import MemoryItem, MemoryQuery


class Memory(Protocol):
    """The only way into memory. Search never bypasses `recall`."""

    async def remember(self, item: MemoryItem) -> None: ...

    async def recall(self, query: MemoryQuery) -> list[MemoryItem]: ...
