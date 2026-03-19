"""Search and CLI tests."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from typing import cast

import pytest

import src.main as main_module
from src.crawler import CrawledPage, QuoteCrawler
from src.indexer import Posting, SearchIndex, build_inverted_index
from src.main import CommandError, SearchCLI, main, run_shell
from src.search import (
    SearchError,
    find_documents,
    parse_query_parts,
    print_term_details,
    suggest_terms,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    """Load an HTML fixture from disk."""
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def build_fixture_pages() -> list[CrawledPage]:
    """Build structured pages from fixture HTML."""
    crawler = QuoteCrawler(politeness_delay=6.0)
    return [
        crawler.parse_page("https://quotes.toscrape.com/", load_fixture("page_1.html")),
        crawler.parse_page("https://quotes.toscrape.com/page/2/", load_fixture("page_2.html")),
    ]


def build_fixture_index() -> SearchIndex:
    """Build a reusable index for search tests."""
    return build_inverted_index(build_fixture_pages(), built_at="2026-03-19T12:00:00Z")


def test_print_term_details_returns_normalised_postings() -> None:
    index = build_fixture_index()

    term_details = print_term_details(index, "GOOD!")
    postings = cast(dict[str, Posting], term_details["postings"])

    assert term_details["term"] == "good"
    assert term_details["document_frequency"] == 1
    assert postings["https://quotes.toscrape.com/"]["term_frequency"] == 2


def test_find_documents_supports_and_queries() -> None:
    index = build_fixture_index()
    query = parse_query_parts(["good", "friends"])

    results = find_documents(index, query)

    assert [result.url for result in results] == ["https://quotes.toscrape.com/"]
    assert results[0].score > 0


def test_find_documents_supports_phrase_queries() -> None:
    index = build_fixture_index()
    positive_query = parse_query_parts(["good friends"])
    negative_query = parse_query_parts(["good conscience"])

    positive_results = find_documents(index, positive_query)
    negative_results = find_documents(index, negative_query)

    assert [result.url for result in positive_results] == ["https://quotes.toscrape.com/"]
    assert negative_results == []


def test_parse_query_parts_rejects_empty_queries() -> None:
    with pytest.raises(SearchError, match="Query cannot be empty"):
        parse_query_parts([])

    with pytest.raises(SearchError, match="Query cannot be empty"):
        parse_query_parts(["   "])


def test_print_term_details_handles_unknown_and_empty_terms() -> None:
    index = build_fixture_index()

    missing = print_term_details(index, "unknown")

    assert missing["document_frequency"] == 0
    assert missing["postings"] == {}

    with pytest.raises(SearchError, match="non-empty word"):
        print_term_details(index, "!!!")


def test_find_documents_and_suggest_terms_handle_unknown_queries() -> None:
    index = build_fixture_index()
    unknown_results = find_documents(index, parse_query_parts(["missing"]))

    assert unknown_results == []
    assert suggest_terms(index, "indiffernce") == ["indifference"]
    assert suggest_terms(index, "!!!") == []


def test_cli_executes_build_load_print_and_find(tmp_path: Path) -> None:
    pages = build_fixture_pages()
    index_path = tmp_path / "index.json"

    class FakeCrawler:
        def crawl(self) -> list[CrawledPage]:
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


def test_cli_handles_help_errors_auto_load_and_suggestions(tmp_path: Path) -> None:
    pages = build_fixture_pages()
    index_path = tmp_path / "index.json"

    class FakeCrawler:
        def crawl(self) -> list[CrawledPage]:
            return pages

    builder = SearchCLI(crawler=FakeCrawler(), index_path=index_path)
    builder.execute(["build"])

    cli = SearchCLI(crawler=FakeCrawler(), index_path=index_path)

    assert cli.execute([]).startswith("Commands:")
    assert cli.execute(["exit"]) == "__EXIT__"
    assert '"term": "good"' in cli.execute(["print", "good"])
    assert "Suggestions: indifference" in cli.execute(["find", "indiffernce"])

    with pytest.raises(CommandError, match="Unknown command"):
        cli.execute(["unknown"])

    with pytest.raises(CommandError, match="find requires one or more query terms"):
        cli.execute(["find"])

    with pytest.raises(CommandError, match="print expects 1 argument"):
        cli.execute(["print", "good", "extra"])


def test_run_shell_prints_help_reports_errors_and_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    inputs = iter(["help", "find", "exit"])
    stdout = StringIO()
    stderr = StringIO()

    def fake_input(_: str) -> str:
        return next(inputs)

    monkeypatch.setattr("builtins.input", fake_input)

    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = run_shell(SearchCLI())

    assert exit_code == 0
    assert "Commands:" in stdout.getvalue()
    assert "find requires one or more query terms." in stderr.getvalue()


def test_run_shell_handles_eof(monkeypatch: pytest.MonkeyPatch) -> None:
    stdout = StringIO()

    def fake_input(_: str) -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", fake_input)

    with redirect_stdout(stdout):
        exit_code = run_shell(SearchCLI())

    assert exit_code == 0
    assert stdout.getvalue() == "\n"


def test_main_handles_help_shell_and_error_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    stdout = StringIO()
    stderr = StringIO()

    with redirect_stdout(stdout):
        assert main(["help"]) == 0

    assert "Commands:" in stdout.getvalue()

    monkeypatch.setattr(main_module, "run_shell", lambda cli: 7)
    assert main([]) == 7

    with redirect_stderr(stderr):
        assert main(["print"]) == 1

    assert "print expects 1 argument" in stderr.getvalue()
