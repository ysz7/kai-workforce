"""The browser adapter, without a browser.

Playwright is an optional extra, so the interesting case on a machine that does
not have it is the message: an employee that reaches for a page it cannot open
should produce an instruction a person can follow, not an ImportError.
"""

from __future__ import annotations

import pytest

from domain.errors import ConfigurationError
from domain.search.models import SearchResult
from infrastructure.browser.playwright_browser import PlaywrightBrowser
from tests.fakes.browser import FakeSearchEngine


def _has_playwright() -> bool:
    try:
        import playwright.async_api  # noqa: F401
    except ImportError:
        return False
    return True


@pytest.mark.skipif(_has_playwright(), reason="Playwright is installed on this machine")
async def test_a_missing_browser_engine_explains_how_to_install_it() -> None:
    with pytest.raises(ConfigurationError, match="playwright install"):
        await PlaywrightBrowser().open("https://example.org")


async def test_search_is_delegated_rather_than_scraped_from_a_results_page() -> None:
    engine = FakeSearchEngine([SearchResult("WAL", "https://sqlite.org/wal.html")])

    results = await PlaywrightBrowser(engine).search("sqlite wal")

    assert results[0].url == "https://sqlite.org/wal.html"
    assert engine.queries[0].text == "sqlite wal"


async def test_a_browser_built_without_a_search_engine_says_so() -> None:
    with pytest.raises(ConfigurationError, match="without a search engine"):
        await PlaywrightBrowser().search("anything")
