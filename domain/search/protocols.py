from __future__ import annotations

from typing import Protocol

from domain.search.models import SearchQuery, SearchResult


class SearchEngine(Protocol):
    async def search(self, query: SearchQuery) -> list[SearchResult]: ...
