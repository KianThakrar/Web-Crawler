"""CLI entry point for the coursework search engine."""

from __future__ import annotations

import json
import shlex
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.crawler import CrawledPage, CrawlerError, QuoteCrawler
from src.indexer import (
    IndexPersistenceError,
    SearchIndex,
    build_inverted_index,
    load_index,
    save_index,
)
from src.search import (
    SearchError,
    find_documents,
    parse_query_parts,
    print_term_details,
    suggest_terms,
)

DEFAULT_INDEX_PATH = Path("data/index.json")


class CommandError(RuntimeError):
    """Raised when the CLI command usage is invalid."""


class CrawlProvider(Protocol):
    """Protocol for dependency-injected crawlers in tests."""

    def crawl(self) -> list[CrawledPage]:
        """Return crawled pages for indexing."""


class SearchCLI:
    """Command runner for the coursework CLI and interactive shell."""

    def __init__(
        self,
        *,
        crawler: CrawlProvider | None = None,
        index_path: str | Path = DEFAULT_INDEX_PATH,
    ) -> None:
        self.crawler = crawler or QuoteCrawler()
        self.index_path = Path(index_path)
        self.loaded_index: SearchIndex | None = None

    def execute(self, args: Sequence[str]) -> str:
        """Execute a single CLI command."""
        if not args:
            return self.help_text()

        command, *command_args = list(args)

        if command == "build":
            self._require_arity(command, command_args, 0)
            return self.build()
        if command == "load":
            self._require_arity(command, command_args, 0)
            return self.load()
        if command == "print":
            self._require_arity(command, command_args, 1)
            return self.print_word(command_args[0])
        if command == "find":
            if not command_args:
                raise CommandError("find requires one or more query terms.")
            return self.find(command_args)
        if command in {"help", "?"}:
            return self.help_text()
        if command in {"exit", "quit"}:
            return "__EXIT__"

        raise CommandError(f"Unknown command: {command}")

    def execute_line(self, line: str) -> str:
        """Parse and execute a shell-style command line."""
        if not line.strip():
            return ""
        return self.execute(shlex.split(line))

    def build(self) -> str:
        """Crawl the site, build the index, and save it to disk."""
        pages = self.crawler.crawl()
        self.loaded_index = build_inverted_index(pages)
        save_index(self.loaded_index, self.index_path)
        return (
            f"Built index with {self.loaded_index.document_count} documents and "
            f"{self.loaded_index.term_count} unique terms at {self.index_path}"
        )

    def load(self) -> str:
        """Load an existing compiled index from disk."""
        self.loaded_index = load_index(self.index_path)
        return (
            f"Loaded index with {self.loaded_index.document_count} documents and "
            f"{self.loaded_index.term_count} unique terms from {self.index_path}"
        )

    def print_word(self, word: str) -> str:
        """Return posting data for a single word."""
        index = self._ensure_index_loaded()
        details = print_term_details(index, word)
        return json.dumps(details, indent=2, sort_keys=True)

    def find(self, query_parts: Sequence[str]) -> str:
        """Return ranked matching pages for a query."""
        index = self._ensure_index_loaded()
        query = parse_query_parts(query_parts)
        results = find_documents(index, query)
        if not results:
            suggestions = suggest_terms(index, query.raw_text)
            if suggestions:
                return "No matching pages found. Suggestions: " + ", ".join(suggestions)
            return "No matching pages found."

        return "\n".join(f"{result.url} (score={result.score:.3f})" for result in results)

    def help_text(self) -> str:
        """Return a concise help summary."""
        return "Commands: build, load, print <word>, find <terms...>, help, exit"

    def _ensure_index_loaded(self) -> SearchIndex:
        if self.loaded_index is None:
            self.loaded_index = load_index(self.index_path)
        return self.loaded_index

    @staticmethod
    def _require_arity(command: str, command_args: Sequence[str], expected: int) -> None:
        if len(command_args) != expected:
            raise CommandError(f"{command} expects {expected} argument(s).")


def run_shell(cli: SearchCLI | None = None) -> int:
    """Run the interactive shell interface."""
    shell = cli or SearchCLI()

    while True:
        try:
            line = input("search> ")
            result = shell.execute_line(line)
            if result == "__EXIT__":
                return 0
            if result:
                print(result)
        except (CommandError, CrawlerError, IndexPersistenceError, SearchError) as exc:
            print(str(exc), file=sys.stderr)
        except EOFError:
            print()
            return 0
        except KeyboardInterrupt:
            print()
            return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the direct CLI or the interactive shell."""
    cli = SearchCLI()
    arguments = list(argv if argv is not None else sys.argv[1:])

    if not arguments:
        return run_shell(cli)

    try:
        result = cli.execute(arguments)
        if result != "__EXIT__":
            print(result)
        return 0
    except (CommandError, CrawlerError, IndexPersistenceError, SearchError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
