"""Web search as its own capability, separate from driving a browser.

Most questions need a list of candidate sources, not a rendered page, and
answering them by opening a browser costs a page load per result. Search is
therefore its own contract, and a browser is one possible way to implement it.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SearchResult:
    title: str
    url: str
    snippet: str = ""


@dataclass(frozen=True, slots=True)
class SearchQuery:
    text: str
    limit: int = 5
