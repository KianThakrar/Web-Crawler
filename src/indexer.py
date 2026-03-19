"""Indexer module for the coursework search engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import re
from typing import TypedDict
import unicodedata

from src.crawler import BASE_URL, CrawledPage


INDEX_SCHEMA_VERSION = 1
TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)?")


class IndexPersistenceError(RuntimeError):
    """Raised when the index file cannot be read or validated."""


class DocumentMetadata(TypedDict):
    """Stored metadata for a crawled page."""

    title: str
    quote_count: int
    word_count: int


class Posting(TypedDict):
    """Posting data for a single term in one document."""

    positions: list[int]
    term_frequency: int


class TermEntry(TypedDict):
    """Term-level index data."""

    document_frequency: int
    postings: dict[str, Posting]


@dataclass(frozen=True)
class SearchIndex:
    """Persisted inverted index with document and term statistics."""

    schema_version: int
    base_url: str
    built_at: str
    document_count: int
    term_count: int
    documents: dict[str, DocumentMetadata]
    terms: dict[str, TermEntry]

    def to_dict(self) -> dict[str, object]:
        """Convert the index to a JSON-serialisable dictionary."""
        return {
            "schema_version": self.schema_version,
            "base_url": self.base_url,
            "built_at": self.built_at,
            "document_count": self.document_count,
            "term_count": self.term_count,
            "documents": self.documents,
            "terms": self.terms,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> SearchIndex:
        """Build a validated search index from a decoded JSON payload."""
        schema_version = payload.get("schema_version")
        if schema_version != INDEX_SCHEMA_VERSION:
            raise IndexPersistenceError(
                f"Unsupported index schema: {schema_version!r}. Expected {INDEX_SCHEMA_VERSION}."
            )

        try:
            base_url = str(payload["base_url"])
            built_at = str(payload["built_at"])
            document_count = int(payload["document_count"])
            term_count = int(payload["term_count"])
            raw_documents = payload["documents"]
            raw_terms = payload["terms"]
        except (KeyError, TypeError, ValueError) as exc:
            raise IndexPersistenceError("Index file is missing required metadata.") from exc

        if not isinstance(raw_documents, dict) or not isinstance(raw_terms, dict):
            raise IndexPersistenceError("Index file contains invalid document or term sections.")

        documents: dict[str, DocumentMetadata] = {}
        for url, metadata in raw_documents.items():
            if not isinstance(url, str) or not isinstance(metadata, dict):
                raise IndexPersistenceError("Document metadata must be stored as object mappings.")

            try:
                documents[url] = DocumentMetadata(
                    title=str(metadata["title"]),
                    quote_count=int(metadata["quote_count"]),
                    word_count=int(metadata["word_count"]),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise IndexPersistenceError("Document metadata entry is invalid.") from exc

        terms: dict[str, TermEntry] = {}
        for term, entry in raw_terms.items():
            if not isinstance(term, str) or not isinstance(entry, dict):
                raise IndexPersistenceError("Term entries must be stored as object mappings.")

            try:
                document_frequency = int(entry["document_frequency"])
                raw_postings = entry["postings"]
            except (KeyError, TypeError, ValueError) as exc:
                raise IndexPersistenceError("Term entry is missing posting data.") from exc

            if not isinstance(raw_postings, dict):
                raise IndexPersistenceError("Term postings must be stored as object mappings.")

            postings: dict[str, Posting] = {}
            for url, posting in raw_postings.items():
                if not isinstance(url, str) or not isinstance(posting, dict):
                    raise IndexPersistenceError("Posting entries must be stored as object mappings.")

                try:
                    positions = [int(position) for position in posting["positions"]]
                    term_frequency = int(posting["term_frequency"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise IndexPersistenceError("Posting entry is invalid.") from exc

                postings[url] = Posting(
                    positions=positions,
                    term_frequency=term_frequency,
                )

            terms[term] = TermEntry(
                document_frequency=document_frequency,
                postings=postings,
            )

        if document_count != len(documents) or term_count != len(terms):
            raise IndexPersistenceError("Index metadata counts do not match the stored data.")

        return cls(
            schema_version=INDEX_SCHEMA_VERSION,
            base_url=base_url,
            built_at=built_at,
            document_count=document_count,
            term_count=term_count,
            documents=documents,
            terms=terms,
        )


def tokenize_text(text: str) -> list[str]:
    """Normalise text and split it into indexable tokens."""
    folded = unicodedata.normalize("NFKD", text.casefold())
    ascii_text = "".join(character for character in folded if not unicodedata.combining(character))
    return TOKEN_PATTERN.findall(ascii_text)


def build_inverted_index(
    pages: list[CrawledPage],
    *,
    built_at: str | None = None,
    base_url: str = BASE_URL,
) -> SearchIndex:
    """Build a deterministic inverted index from structured crawled pages."""
    documents: dict[str, DocumentMetadata] = {}
    terms: dict[str, TermEntry] = {}

    for page in pages:
        tokens = tokenize_text(page.search_text())
        documents[page.url] = DocumentMetadata(
            title=page.title,
            quote_count=len(page.quotes),
            word_count=len(tokens),
        )

        for position, token in enumerate(tokens):
            term_entry = terms.setdefault(
                token,
                TermEntry(document_frequency=0, postings={}),
            )
            posting = term_entry["postings"].get(page.url)
            if posting is None:
                posting = Posting(positions=[], term_frequency=0)
                term_entry["postings"][page.url] = posting
                term_entry["document_frequency"] += 1

            posting["term_frequency"] += 1
            posting["positions"].append(position)

    ordered_documents = {
        url: documents[url]
        for url in sorted(documents)
    }
    ordered_terms = {
        term: TermEntry(
            document_frequency=terms[term]["document_frequency"],
            postings={
                url: terms[term]["postings"][url]
                for url in sorted(terms[term]["postings"])
            },
        )
        for term in sorted(terms)
    }

    return SearchIndex(
        schema_version=INDEX_SCHEMA_VERSION,
        base_url=base_url,
        built_at=built_at or datetime.now(UTC).isoformat(),
        document_count=len(ordered_documents),
        term_count=len(ordered_terms),
        documents=ordered_documents,
        terms=ordered_terms,
    )


def save_index(index: SearchIndex, output_path: str | Path) -> None:
    """Persist the compiled index to disk as a single JSON file."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index.to_dict(), indent=2, sort_keys=True), encoding="utf-8")


def load_index(input_path: str | Path) -> SearchIndex:
    """Load a previously built index from disk."""
    path = Path(input_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise IndexPersistenceError(f"Index file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise IndexPersistenceError(f"Index file is not valid JSON: {path}") from exc

    if not isinstance(payload, dict):
        raise IndexPersistenceError("Index file must contain a JSON object.")

    return SearchIndex.from_dict(payload)
