from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from domain.search.models import SearchResult


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
    """Driving a page.

    `search` stays on this contract because a caller with a browser should not
    also need a search engine to be useful. An implementation is expected to
    delegate it to a `SearchEngine` rather than scrape a results page itself:
    search is its own capability (see `domain.search`).
    """

    async def search(self, query: str) -> list[SearchResult]: ...

    async def open(self, url: str) -> None: ...

    async def extract(self) -> ExtractResult: ...
