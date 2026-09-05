"""Web search without a key.

An employee that cannot search is an employee working from what its model
remembers, which is how Phase 3 ended up citing a URL that does not exist. The
cheapest fix that works on a fresh checkout is a keyless engine: this one posts
to the HTML endpoint and reads the result list out of the markup.

Scraping markup is a trade, and the trade is stated here rather than
discovered later: no key, no quota, no account against a format that can change
without warning. The `SearchEngine` protocol is what the rest of the system
depends on, so replacing this with a paid API is one adapter and one line in the
container.
"""

from __future__ import annotations

from html import unescape
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlparse

import httpx

from domain.errors import ProviderError
from domain.search.models import SearchQuery, SearchResult
from infrastructure.llm.errors import translate_transport_error
from infrastructure.observability.logging import get_logger

log = get_logger(__name__)

ENDPOINT = "https://html.duckduckgo.com/html/"

#: The endpoint answers a browser and refuses an unidentified client.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)


class _ResultParser(HTMLParser):
    """Pulls (title, url, snippet) out of the results markup.

    Written against the classes the endpoint uses rather than a general HTML
    library, so the whole search path stays inside the standard library plus the
    HTTP client the project already has.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[SearchResult] = []
        self._collecting: str | None = None
        self._title: list[str] = []
        self._snippet: list[str] = []
        self._url = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key: value or "" for key, value in attrs}
        classes = attributes.get("class", "").split()
        if tag == "a" and "result__a" in classes:
            self._flush()
            self._url = _clean_url(attributes.get("href", ""))
            self._collecting = "title"
        elif tag == "a" and "result__snippet" in classes:
            self._collecting = "snippet"

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._collecting == "snippet":
            self._flush()
        elif tag == "a" and self._collecting == "title":
            self._collecting = None

    def handle_data(self, data: str) -> None:
        if self._collecting == "title":
            self._title.append(data)
        elif self._collecting == "snippet":
            self._snippet.append(data)

    def close(self) -> None:
        super().close()
        self._flush()

    def _flush(self) -> None:
        title = unescape("".join(self._title)).strip()
        if title and self._url:
            self.results.append(
                SearchResult(
                    title=title,
                    url=self._url,
                    snippet=unescape("".join(self._snippet)).strip(),
                )
            )
        self._title, self._snippet, self._url, self._collecting = [], [], "", None


def _clean_url(href: str) -> str:
    """Unwrap the redirect the endpoint wraps every result in."""
    if href.startswith("//"):
        href = f"https:{href}"
    parsed = urlparse(href)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg")
        if target:
            return target[0]
    return href


class DuckDuckGoSearch:
    """Implements `domain.search.protocols.SearchEngine`."""

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        timeout_seconds: float = 20.0,
        endpoint: str = ENDPOINT,
    ) -> None:
        self._client = client
        self._owns_client = client is None
        self._timeout = timeout_seconds
        self._endpoint = endpoint

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout, follow_redirects=True)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None

    async def search(self, query: SearchQuery) -> list[SearchResult]:
        client = self._ensure_client()
        try:
            response = await client.post(
                self._endpoint,
                data={"q": query.text},
                headers={"User-Agent": USER_AGENT},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise ProviderError(
                f"Search returned HTTP {error.response.status_code}"
            ) from error
        except httpx.HTTPError as error:
            raise translate_transport_error(error, provider="search") from error

        parser = _ResultParser()
        parser.feed(response.text)
        parser.close()
        log.info("search.completed", query_length=len(query.text), results=len(parser.results))
        return parser.results[: max(query.limit, 1)]
