"""Search and CLI tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.crawler import QuoteCrawler
from src.indexer import build_inverted_index
from src.main import SearchCLI
from src.search import SearchError, find_documents, parse_query_parts, print_term_details


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    """Load an HTML fixture from disk."""
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def build_fixture_pages() -> list:
    """Build structured pages from fixture HTML."""
    crawler = QuoteCrawler(politeness_delay=6.0)
    return [
        crawler.parse_page("https://quotes.toscrape.com/", load_fixture("page_1.html")),
        crawler.parse_page("https://quotes.toscrape.com/page/2/", load_fixture("page_2.html")),
    ]


def build_fixture_index():
    """Build a reusable index for search tests."""
    return build_inverted_index(build_fixture_pages(), built_at="2026-03-19T12:00:00Z")


def test_print_term_details_returns_normalised_postings() -> None:
    index = build_fixture_index()

    term_details = print_term_details(index, "GOOD!")

    assert term_details["term"] == "good"
    assert term_details["document_frequency"] == 1
    assert term_details["postings"]["https://quotes.toscrape.com/"]["term_frequency"] == 2


def test_find_documents_supports_and_queries() -> None:
    index = build_fixture_index()
    query = parse_query_parts(["good", "friends"])

    results = find_documents(index, query)

    assert [result.url for result in results] == ["https://quotes.toscrape.com/"]
    assert results[0].score > 0


def test_find_documents_supports_phrase_queries() -> None:
    index = build_fixture_index()
    positive_query = parse_query_parts(["good friends"])
    negative_query = parse_query_parts(["friends good"])

    positive_results = find_documents(index, positive_query)
    negative_results = find_documents(index, negative_query)

    assert [result.url for result in positive_results] == ["https://quotes.toscrape.com/"]
    assert negative_results == []


def test_parse_query_parts_rejects_empty_queries() -> None:
    with pytest.raises(SearchError, match="Query cannot be empty"):
        parse_query_parts([])


def test_cli_executes_build_load_print_and_find(tmp_path: Path) -> None:
    pages = build_fixture_pages()
    index_path = tmp_path / "index.json"

    class FakeCrawler:
        def crawl(self) -> list:
            return pages

    cli = SearchCLI(crawler=FakeCrawler(), index_path=index_path)

    build_output = cli.execute(["build"])
    load_output = cli.execute(["load"])
    print_output = cli.execute(["print", "good"])
    find_output = cli.execute(["find", "good", "friends"])
    phrase_output = cli.execute_line('find "good friends"')

    assert "Built index with 2 documents" in build_output
    assert "Loaded index with 2 documents" in load_output
    assert '"term": "good"' in print_output
    assert "https://quotes.toscrape.com/" in find_output
    assert "https://quotes.toscrape.com/" in phrase_output
