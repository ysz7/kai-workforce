from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class SearchResult:
    title: str
    url: str
    snippet: str = ""


@dataclass(frozen=True, slots=True)
class ExtractResult:
    url: str
    title: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


class Page(Protocol):
    @property
    def url(self) -> str: ...

    @property
    def title(self) -> str: ...


class Browser(Protocol):
    async def search(self, query: str) -> list[SearchResult]: ...

    async def open(self, url: str) -> None: ...

    async def extract(self) -> ExtractResult: ...
