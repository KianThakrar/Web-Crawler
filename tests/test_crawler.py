"""Crawler tests."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
import requests

from src.crawler import CrawlerError, QuoteCrawler

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    """Load an HTML fixture from disk."""
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def test_parse_page_extracts_quotes_and_next_url() -> None:
    crawler = QuoteCrawler(politeness_delay=6.0)

    page = crawler.parse_page("https://quotes.toscrape.com/", load_fixture("page_1.html"))

    assert page.url == "https://quotes.toscrape.com/"
    assert page.title == "Quotes to Scrape"
    assert len(page.quotes) == 2
    assert page.quotes[0].author == "Mark Twain"
    assert page.quotes[0].tags == ["friends", "books"]
    assert "good books" in page.quotes[0].text.casefold()
    assert page.next_url == "https://quotes.toscrape.com/page/2/"
    assert page.is_terminal is False


def test_parse_page_marks_no_quotes_page_as_terminal() -> None:
    crawler = QuoteCrawler(politeness_delay=6.0)

    page = crawler.parse_page(
        "https://quotes.toscrape.com/page/3/",
        load_fixture("page_empty.html"),
    )

    assert page.quotes == []
    assert page.next_url is None
    assert page.is_terminal is True


def test_parse_page_skips_incomplete_quotes_and_defaults_title() -> None:
    crawler = QuoteCrawler(politeness_delay=6.0)
    malformed_html = """
    <html>
      <body>
        <div class="quote">
          <span class="text">Only text, no author</span>
        </div>
      </body>
    </html>
    """

    page = crawler.parse_page("https://quotes.toscrape.com/broken/", malformed_html)

    assert page.title == "Untitled page"
    assert page.quotes == []
    assert page.next_url is None


def test_crawl_follows_pagination_and_waits_between_requests() -> None:
    fixture_map = {
        "https://quotes.toscrape.com/": load_fixture("page_1.html"),
        "https://quotes.toscrape.com/page/2/": load_fixture("page_2.html"),
    }
    current_time = {"value": 100.0}
    sleep_calls: list[float] = []
    fetched_urls: list[str] = []

    def fake_clock() -> float:
        return current_time["value"]

    def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        current_time["value"] += seconds

    def fake_fetch(url: str) -> str:
        fetched_urls.append(url)
        current_time["value"] += 0.25
        return fixture_map[url]

    crawler = QuoteCrawler(
        politeness_delay=6.0,
        clock=fake_clock,
        sleeper=fake_sleep,
    )

    pages = crawler.crawl(start_url="https://quotes.toscrape.com/", fetch_html=fake_fetch)

    assert [page.url for page in pages] == list(fixture_map)
    assert fetched_urls == list(fixture_map)
    assert sleep_calls == [5.75]


def test_crawl_stops_when_terminal_page_is_reached() -> None:
    fixture_map = {
        "https://quotes.toscrape.com/page/10/": load_fixture("page_empty.html"),
    }
    crawler = QuoteCrawler(politeness_delay=6.0)

    pages = crawler.crawl(
        start_url="https://quotes.toscrape.com/page/10/",
        fetch_html=lambda url: fixture_map[url],
    )

    assert len(pages) == 1
    assert pages[0].is_terminal is True


def test_crawl_raises_clear_error_when_fetch_fails() -> None:
    crawler = QuoteCrawler(politeness_delay=6.0)

    def fake_fetch(_: str) -> str:
        raise RuntimeError("boom")

    with pytest.raises(CrawlerError, match="Failed to fetch"):
        crawler.crawl(start_url="https://quotes.toscrape.com/", fetch_html=fake_fetch)


def test_crawl_preserves_existing_crawler_errors() -> None:
    crawler = QuoteCrawler(politeness_delay=6.0)

    def fake_fetch(_: str) -> str:
        raise CrawlerError("already wrapped")

    with pytest.raises(CrawlerError, match="already wrapped"):
        crawler.crawl(start_url="https://quotes.toscrape.com/", fetch_html=fake_fetch)


def test_fetch_html_retries_before_success() -> None:
    class FakeResponse:
        def __init__(self, text: str, *, fail: bool = False) -> None:
            self.text = text
            self.fail = fail

        def raise_for_status(self) -> None:
            if self.fail:
                raise requests.HTTPError("bad status")

    class FakeSession:
        def __init__(self) -> None:
            self.calls = 0

        def get(self, url: str, timeout: float) -> FakeResponse:
            self.calls += 1
            assert url == "https://quotes.toscrape.com/"
            assert timeout == 10.0
            if self.calls == 1:
                raise requests.Timeout("slow")
            return FakeResponse("<html>ok</html>")

    session = FakeSession()
    crawler = QuoteCrawler(
        politeness_delay=6.0,
        session=cast(requests.Session, session),
        max_retries=2,
    )

    html = crawler.fetch_html("https://quotes.toscrape.com/")

    assert html == "<html>ok</html>"
    assert session.calls == 2


def test_fetch_html_raises_after_exhausting_retries() -> None:
    class FakeSession:
        def get(self, url: str, timeout: float) -> str:
            del url, timeout
            raise requests.Timeout("slow")

    crawler = QuoteCrawler(
        politeness_delay=6.0,
        session=cast(requests.Session, FakeSession()),
        max_retries=2,
    )

    with pytest.raises(CrawlerError, match="after 2 attempts"):
        crawler.fetch_html("https://quotes.toscrape.com/")
