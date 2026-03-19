"""Crawler module for the coursework search engine."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic, sleep
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://quotes.toscrape.com/"


class CrawlerError(RuntimeError):
    """Raised when the crawler cannot retrieve or parse the target pages."""


@dataclass(frozen=True)
class QuoteRecord:
    """Structured quote content extracted from a page."""

    text: str
    author: str
    tags: list[str]

    def search_text(self) -> str:
        """Return the relevant text fields for indexing."""
        return " ".join([self.text, self.author, *self.tags])


@dataclass(frozen=True)
class CrawledPage:
    """Represents a single crawled listing page."""

    url: str
    title: str
    quotes: list[QuoteRecord]
    next_url: str | None
    is_terminal: bool

    def search_text(self) -> str:
        """Return the aggregated text that should be indexed for this page."""
        quote_segments = [quote.search_text() for quote in self.quotes]
        return " ".join([self.title, *quote_segments]).strip()


class QuoteCrawler:
    """Crawl the paginated quote listing pages from quotes.toscrape.com."""

    def __init__(
        self,
        *,
        base_url: str = BASE_URL,
        politeness_delay: float = 6.0,
        timeout: float = 10.0,
        max_retries: int = 3,
        session: requests.Session | None = None,
        clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        self.base_url = base_url
        self.politeness_delay = politeness_delay
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = session or requests.Session()
        self.clock = clock
        self.sleeper = sleeper
        self._last_request_started_at: float | None = None

    def parse_page(self, url: str, html: str) -> CrawledPage:
        """Parse a quote listing page and return structured content."""
        soup = BeautifulSoup(html, "html.parser")
        title = soup.title.get_text(strip=True) if soup.title else "Untitled page"
        quotes: list[QuoteRecord] = []

        for quote_element in soup.select("div.quote"):
            text_element = quote_element.select_one("span.text")
            author_element = quote_element.select_one("small.author")
            if text_element is None or author_element is None:
                continue

            tags = [tag.get_text(strip=True) for tag in quote_element.select("a.tag")]
            quotes.append(
                QuoteRecord(
                    text=text_element.get_text(" ", strip=True),
                    author=author_element.get_text(" ", strip=True),
                    tags=tags,
                )
            )

        next_anchor = soup.select_one("li.next a")
        next_url = None
        if next_anchor is not None and next_anchor.get("href"):
            next_url = urljoin(url, str(next_anchor["href"]))

        page_text = soup.get_text(" ", strip=True).casefold()
        is_terminal = not quotes and "no quotes found!" in page_text

        return CrawledPage(
            url=url,
            title=title,
            quotes=quotes,
            next_url=next_url,
            is_terminal=is_terminal,
        )

    def crawl(
        self,
        *,
        start_url: str | None = None,
        fetch_html: Callable[[str], str] | None = None,
    ) -> list[CrawledPage]:
        """Crawl the paginated quote listing pages until the chain ends."""
        current_url: str | None = start_url or self.base_url
        visited: set[str] = set()
        pages: list[CrawledPage] = []

        while current_url is not None and current_url not in visited:
            html = self._fetch_page_html(current_url, fetch_html)
            page = self.parse_page(current_url, html)
            pages.append(page)
            visited.add(current_url)

            if page.is_terminal:
                break

            current_url = page.next_url

        return pages

    def fetch_html(self, url: str) -> str:
        """Fetch a page over HTTP with retry handling."""
        last_exception: requests.RequestException | None = None

        for _ in range(self.max_retries):
            try:
                response = self.session.get(url, timeout=self.timeout)
                response.raise_for_status()
                return response.text
            except requests.RequestException as exc:
                last_exception = exc

        raise CrawlerError(
            f"Failed to fetch {url!r} after {self.max_retries} attempts."
        ) from last_exception

    def _fetch_page_html(
        self,
        url: str,
        fetch_html: Callable[[str], str] | None,
    ) -> str:
        self._wait_for_politeness()
        self._last_request_started_at = self.clock()
        fetcher = fetch_html or self.fetch_html

        try:
            return fetcher(url)
        except CrawlerError:
            raise
        except Exception as exc:  # pragma: no cover - defensive wrapper
            raise CrawlerError(f"Failed to fetch {url!r}: {exc}") from exc

    def _wait_for_politeness(self) -> None:
        if self._last_request_started_at is None:
            return

        elapsed = self.clock() - self._last_request_started_at
        remaining = self.politeness_delay - elapsed
        if remaining > 0:
            self.sleeper(remaining)
