"""Search and browsing, on fixtures. No test in this suite reaches the network."""

from __future__ import annotations

import httpx
import pytest

from domain.search.models import SearchQuery, SearchResult
from infrastructure.search.duckduckgo import DuckDuckGoSearch
from infrastructure.tools.web import BrowserExtractTool, BrowserOpenTool, WebSearchTool
from tests.fakes.browser import FakeBrowser, FakeSearchEngine

RESULTS_HTML = """
<div class="result results_links">
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fsqlite.org%2Fwal.html&rut=1">
    Write-Ahead Logging
  </a>
  <a class="result__snippet">Readers do not block the writer.</a>
</div>
<div class="result results_links">
  <a class="result__a" href="https://example.org/locking">Locking</a>
  <a class="result__snippet">How SQLite locks.</a>
</div>
"""


async def test_search_returns_titles_urls_and_snippets() -> None:
    tool = WebSearchTool(FakeSearchEngine())

    result = await tool.execute({"query": "sqlite wal"})

    assert result.success
    assert result.output["count"] == 2
    assert result.output["results"][0]["url"] == "https://sqlite.org/wal.html"


async def test_search_asks_for_no_more_results_than_the_cap() -> None:
    engine = FakeSearchEngine()

    await WebSearchTool(engine).execute({"query": "x", "limit": 99})

    assert engine.queries[0].limit == 10


async def test_finding_nothing_is_a_successful_call_with_nothing_in_it() -> None:
    """Reporting an empty search as a failure invites the model to retry it forever."""
    result = await WebSearchTool(FakeSearchEngine(results=[])).execute({"query": "x"})

    assert result.success
    assert result.output["count"] == 0


async def test_a_page_is_opened_and_then_read() -> None:
    browser = FakeBrowser()

    opened = await BrowserOpenTool(browser).execute({"url": "https://sqlite.org/wal.html"})
    extracted = await BrowserExtractTool(browser).execute({})

    assert opened.success
    assert extracted.output["title"] == "Write-Ahead Logging"
    assert extracted.output["text"] == "Readers do not block."


async def test_reading_before_opening_is_reported_to_the_model() -> None:
    result = await BrowserExtractTool(FakeBrowser()).execute({})

    assert not result.success
    assert "No page is open" in result.error


async def test_a_page_that_does_not_load_is_a_failed_step_not_a_dead_task() -> None:
    result = await BrowserOpenTool(FakeBrowser()).execute({"url": "https://nowhere.invalid"})

    assert not result.success


# --- The keyless search engine, against a stubbed transport --------------------


async def test_results_are_read_out_of_the_markup_and_unwrapped() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=RESULTS_HTML))
    engine = DuckDuckGoSearch(httpx.AsyncClient(transport=transport))

    results = await engine.search(SearchQuery(text="sqlite wal", limit=5))

    assert results == [
        SearchResult("Write-Ahead Logging", "https://sqlite.org/wal.html",
                     "Readers do not block the writer."),
        SearchResult("Locking", "https://example.org/locking", "How SQLite locks."),
    ]


async def test_the_result_limit_is_honoured() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=RESULTS_HTML))
    engine = DuckDuckGoSearch(httpx.AsyncClient(transport=transport))

    assert len(await engine.search(SearchQuery(text="x", limit=1))) == 1


async def test_a_refused_request_becomes_a_provider_error() -> None:
    from domain.errors import ProviderError

    transport = httpx.MockTransport(lambda request: httpx.Response(429, text="slow down"))
    engine = DuckDuckGoSearch(httpx.AsyncClient(transport=transport))

    with pytest.raises(ProviderError, match="429"):
        await engine.search(SearchQuery(text="x"))


async def test_a_wrong_argument_name_comes_back_with_the_right_call_shape() -> None:
    """Observed with a small local model: without the shape, it guesses forever."""
    result = await BrowserOpenTool(FakeBrowser()).execute({"id": "https://sqlite.org/wal.html"})

    assert not result.success
    assert 'Call browser.open like this: {"url": <string>}' in result.error


async def test_a_correct_call_with_a_spurious_extra_still_opens_the_page() -> None:
    """Also observed: the same model garnishes good calls with keys of its own."""
    browser = FakeBrowser()

    result = await BrowserOpenTool(browser).execute(
        {"url": "https://sqlite.org/wal.html", "cursor": 0}
    )

    assert result.success
    assert browser.opened == ["https://sqlite.org/wal.html"]
    assert result.output["ignored_arguments"] == ["cursor"]
