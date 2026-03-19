"""Indexer tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.crawler import QuoteCrawler
from src.indexer import (
    IndexPersistenceError,
    SearchIndex,
    build_inverted_index,
    load_index,
    save_index,
    tokenize_text,
)


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    """Load an HTML fixture from disk."""
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def build_fixture_pages() -> list:
    """Build structured pages from the fixture HTML documents."""
    crawler = QuoteCrawler(politeness_delay=6.0)
    return [
        crawler.parse_page("https://quotes.toscrape.com/", load_fixture("page_1.html")),
        crawler.parse_page("https://quotes.toscrape.com/page/2/", load_fixture("page_2.html")),
    ]


def test_tokenize_text_normalises_case_punctuation_and_accents() -> None:
    tokens = tokenize_text("Good, CAFE cafe! Caf\u00e9-good.")

    assert tokens == ["good", "cafe", "cafe", "cafe", "good"]


def test_build_inverted_index_tracks_term_statistics() -> None:
    index = build_inverted_index(build_fixture_pages(), built_at="2026-03-19T12:00:00Z")

    assert isinstance(index, SearchIndex)
    assert index.document_count == 2
    assert index.documents["https://quotes.toscrape.com/"]["word_count"] == 35
    assert index.terms["good"]["document_frequency"] == 1
    assert index.terms["good"]["postings"]["https://quotes.toscrape.com/"]["term_frequency"] == 2
    assert index.terms["good"]["postings"]["https://quotes.toscrape.com/"]["positions"] == [3, 5]
    assert index.terms["mark"]["document_frequency"] == 2


def test_save_and_load_index_round_trip(tmp_path: Path) -> None:
    index = build_inverted_index(build_fixture_pages(), built_at="2026-03-19T12:00:00Z")
    output_path = tmp_path / "index.json"

    save_index(index, output_path)
    loaded_index = load_index(output_path)

    assert loaded_index == index
    serialised = json.loads(output_path.read_text(encoding="utf-8"))
    assert serialised["schema_version"] == 1
    assert serialised["document_count"] == 2


def test_load_index_rejects_invalid_schema(tmp_path: Path) -> None:
    broken_index = tmp_path / "broken.json"
    broken_index.write_text('{"schema_version": 999}', encoding="utf-8")

    with pytest.raises(IndexPersistenceError, match="Unsupported index schema"):
        load_index(broken_index)
