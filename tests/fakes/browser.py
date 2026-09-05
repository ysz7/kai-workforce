"""A browser and a search engine on fixtures, so the suite never leaves the machine."""

from __future__ import annotations

from domain.browser.protocols import ExtractResult
from domain.errors import ProviderError
from domain.search.models import SearchQuery, SearchResult


class FakeSearchEngine:
    """Implements `domain.search.protocols.SearchEngine`."""

    def __init__(self, results: list[SearchResult] | None = None) -> None:
        self.results = results if results is not None else [
            SearchResult("Write-Ahead Logging", "https://sqlite.org/wal.html", "WAL mode."),
            SearchResult("SQLite locking", "https://sqlite.org/lockingv3.html", "Locking."),
        ]
        self.queries: list[SearchQuery] = []

    async def search(self, query: SearchQuery) -> list[SearchResult]:
        self.queries.append(query)
        return self.results[: query.limit]


class FakeBrowser:
    """Implements `domain.browser.protocols.Browser` over a fixed set of pages."""

    def __init__(
        self,
        pages: dict[str, tuple[str, str]] | None = None,
        *,
        search_engine: FakeSearchEngine | None = None,
    ) -> None:
        #: url -> (title, text)
        self.pages = pages or {
            "https://sqlite.org/wal.html": ("Write-Ahead Logging", "Readers do not block."),
        }
        self._search = search_engine or FakeSearchEngine()
        self.opened: list[str] = []
        self.current: str | None = None

    async def search(self, query: str) -> list[SearchResult]:
        return await self._search.search(SearchQuery(text=query))

    async def open(self, url: str) -> None:
        if url not in self.pages:
            raise ProviderError(f"Could not open {url}: no such page")
        self.opened.append(url)
        self.current = url

    async def extract(self) -> ExtractResult:
        if self.current is None:
            raise ProviderError("No page is open")
        title, text = self.pages[self.current]
        return ExtractResult(
            url=self.current, title=title, text=text, metadata={"truncated": False}
        )
