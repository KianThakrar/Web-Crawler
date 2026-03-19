"""Search module for the coursework search engine."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from difflib import get_close_matches

from src.indexer import Posting, SearchIndex, tokenize_text


class SearchError(RuntimeError):
    """Raised when a query cannot be parsed or executed."""


@dataclass(frozen=True)
class ParsedQuery:
    """Normalised representation of a CLI query."""

    raw_text: str
    terms: list[str]
    phrase_terms: list[str] | None = None

    @property
    def is_phrase(self) -> bool:
        """Return whether the query should enforce contiguous positions."""
        return self.phrase_terms is not None


@dataclass(frozen=True)
class SearchResult:
    """Ranked document returned from a query."""

    url: str
    score: float
    matched_terms: list[str]


def parse_query_parts(parts: Sequence[str]) -> ParsedQuery:
    """Parse CLI query parts into normalised term tokens."""
    if not parts:
        raise SearchError("Query cannot be empty.")

    raw_parts = [part for part in parts if part.strip()]
    if not raw_parts:
        raise SearchError("Query cannot be empty.")

    raw_text = " ".join(raw_parts).strip()
    if len(raw_parts) == 1 and any(character.isspace() for character in raw_parts[0]):
        phrase_terms = tokenize_text(raw_parts[0])
        if not phrase_terms:
            raise SearchError("Query cannot be empty.")
        return ParsedQuery(raw_text=raw_text, terms=phrase_terms, phrase_terms=phrase_terms)

    terms: list[str] = []
    for part in raw_parts:
        terms.extend(tokenize_text(part))

    if not terms:
        raise SearchError("Query cannot be empty.")

    return ParsedQuery(raw_text=raw_text, terms=terms)


def print_term_details(index: SearchIndex, raw_term: str) -> dict[str, object]:
    """Return deterministic posting details for a single term."""
    tokens = tokenize_text(raw_term)
    if not tokens:
        raise SearchError("Print command requires a non-empty word.")

    term = tokens[0]
    entry = index.terms.get(term)
    if entry is None:
        return {
            "term": term,
            "document_frequency": 0,
            "postings": {},
        }

    return {
        "term": term,
        "document_frequency": entry["document_frequency"],
        "postings": entry["postings"],
    }


def find_documents(index: SearchIndex, query: ParsedQuery) -> list[SearchResult]:
    """Find ranked documents matching all query terms."""
    postings_per_term: list[dict[str, Posting]] = []
    for term in query.terms:
        term_entry = index.terms.get(term)
        if term_entry is None:
            return []
        postings_per_term.append(term_entry["postings"])

    if any(not postings for postings in postings_per_term):
        return []

    candidate_urls = set(postings_per_term[0])
    for postings in postings_per_term[1:]:
        candidate_urls &= set(postings)

    if query.is_phrase and query.phrase_terms is not None:
        candidate_urls = {
            url
            for url in candidate_urls
            if _document_contains_phrase(index, url, query.phrase_terms)
        }

    results: list[SearchResult] = []
    for url in sorted(candidate_urls):
        score = _score_document(index, url, query.terms)
        if query.is_phrase:
            score += 1.0
        results.append(SearchResult(url=url, score=score, matched_terms=list(query.terms)))

    return sorted(results, key=lambda result: (-result.score, result.url))


def suggest_terms(index: SearchIndex, raw_query: str) -> list[str]:
    """Return close indexed terms for an unsuccessful query."""
    query_tokens = tokenize_text(raw_query)
    if not query_tokens:
        return []

    suggestions: list[str] = []
    for token in query_tokens:
        suggestions.extend(get_close_matches(token, index.terms.keys(), n=3, cutoff=0.75))

    seen: set[str] = set()
    ordered_suggestions: list[str] = []
    for suggestion in suggestions:
        if suggestion not in seen:
            seen.add(suggestion)
            ordered_suggestions.append(suggestion)

    return ordered_suggestions


def _document_contains_phrase(index: SearchIndex, url: str, phrase_terms: list[str]) -> bool:
    first_positions = index.terms[phrase_terms[0]]["postings"][url]["positions"]
    remaining_position_sets = [
        set(index.terms[term]["postings"][url]["positions"]) for term in phrase_terms[1:]
    ]

    for start_position in first_positions:
        if all(
            start_position + offset in positions
            for offset, positions in enumerate(remaining_position_sets, start=1)
        ):
            return True

    return False


def _score_document(index: SearchIndex, url: str, terms: Sequence[str]) -> float:
    score = 0.0

    for term in terms:
        entry = index.terms[term]
        posting = entry["postings"][url]
        term_frequency = posting["term_frequency"]
        inverse_document_frequency = (
            math.log((1 + index.document_count) / (1 + entry["document_frequency"])) + 1.0
        )
        score += (1.0 + math.log(term_frequency)) * inverse_document_frequency

    return score
