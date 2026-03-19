# COMP3011 Coursework 2: Search Engine Tool

Search engine coursework for `COMP3011 Web Services and Web Data`.
The tool crawls `https://quotes.toscrape.com/`, builds a positional inverted index, saves it to disk, and exposes the required `build`, `load`, `print`, and `find` commands through a command-line shell.

## Features

- Required coursework commands: `build`, `load`, `print <word>`, `find <terms...>`
- Polite crawler with a `>= 6` second delay between live requests
- Positional inverted index with:
  - document frequency
  - term frequency
  - token positions
  - per-document metadata
- Case-insensitive token normalisation with punctuation stripping and accent folding
- Ranked retrieval using TF-IDF scoring
- Exact phrase search for quoted queries such as `find "good friends"`
- Query suggestions when a query misses the index
- Interactive shell for the demo plus direct subcommands for automation and testing
- CI workflow with linting, type-checking, and automated tests

## Repository Layout

This repository keeps the coursework brief's required structure as the primary code layout:

```text
.
├── src/
│   ├── crawler.py
│   ├── indexer.py
│   ├── search.py
│   └── main.py
├── tests/
│   ├── fixtures/
│   ├── test_crawler.py
│   ├── test_indexer.py
│   └── test_search.py
├── data/
├── .github/workflows/ci.yml
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml
└── README.md
```

## Architecture

### `src/crawler.py`

- Crawls the paginated quote listing pages only
- Parses quote text, authors, tags, and pagination links
- Enforces the politeness window for live requests
- Retries transient HTTP failures before failing clearly

### `src/indexer.py`

- Normalises text into consistent tokens
- Builds a deterministic positional inverted index
- Stores document metadata and term statistics
- Saves and loads a single JSON index file under `data/`

### `src/search.py`

- Parses CLI queries
- Performs AND-based retrieval for multi-word queries
- Applies TF-IDF ranking
- Supports phrase matching using positional postings
- Suggests close indexed terms for mistyped queries

### `src/main.py`

- Runs the interactive shell used in the coursework demo
- Supports direct commands for scripts and CI
- Loads the saved index automatically when `print` or `find` are run in a fresh process

## Installation

### Runtime dependencies

```bash
python3 -m pip install -r requirements.txt
```

### Development dependencies

```bash
python3 -m pip install -r requirements-dev.txt
```

## Usage

Run the interactive shell:

```bash
python3 src/main.py
```

Example shell session:

```text
search> build
search> load
search> print nonsense
search> find indifference
search> find good friends
search> find "good friends"
search> exit
```

Run direct commands:

```bash
python3 src/main.py build
python3 src/main.py load
python3 src/main.py print nonsense
python3 src/main.py find indifference
python3 src/main.py find good friends
python3 src/main.py find "good friends"
```

### Command Behaviour

#### `build`

- Crawls the target website
- Builds the inverted index
- Saves it to `data/index.json`

#### `load`

- Loads `data/index.json` into memory
- Reports the number of indexed documents and terms

#### `print <word>`

- Prints the posting list for a normalised term
- Includes document frequency, term frequency, and positions

#### `find <terms...>`

- Returns page URLs containing all terms in the query
- Uses TF-IDF ranking for ordering
- Supports exact phrase matching when the query is quoted
- Returns spelling suggestions when no match is found

## Example Output

`print good`

```json
{
  "document_frequency": 1,
  "postings": {
    "https://quotes.toscrape.com/": {
      "positions": [
        3,
        5
      ],
      "term_frequency": 2
    }
  },
  "term": "good"
}
```

`find good friends`

```text
https://quotes.toscrape.com/ (score=5.759)
```

## Testing

Run the full test suite:

```bash
python3 -m pytest -p no:capture
```

Run coverage:

```bash
python3 -m pytest -p no:capture --cov=src --cov-report=term-missing --cov-fail-under=90
```

Run static checks:

```bash
ruff check .
mypy
```

Current automated quality gate status:

- `ruff check .`: passing
- `mypy`: passing
- test coverage: `94.68%`

## CI

GitHub Actions runs the following on pushes and pull requests:

- `ruff check .`
- `ruff format --check .`
- `mypy`
- `pytest --cov=src --cov-report=term-missing --cov-fail-under=90`

## Design Rationale

### Why an inverted index?

An inverted index gives fast query-time lookup because each term maps directly to the pages that contain it. This is more appropriate than scanning every document for each query.

### Why positional postings?

Positions support both:

- richer debugging for the `print` command
- phrase search using contiguous token matching

### Why TF-IDF?

TF-IDF improves result ordering beyond simple set membership by rewarding terms that are frequent in a document but less common across the corpus. This supports the outstanding-grade criterion for features beyond the minimum brief.

## Complexity Notes

- Crawling: `O(P)` page fetches, where `P` is the number of crawled listing pages
- Index build: `O(T)` over the total number of tokens
- Single-term lookup: `O(1)` average hash lookup plus posting traversal
- Multi-term AND query: proportional to the intersected posting sizes
- Phrase query: posting intersection plus positional checks across candidate documents

## Benchmarking Approach

For coursework evidence, benchmark the project using:

1. fresh index build time
2. index load time
3. representative single-term, multi-term, and phrase queries

Recommended command pattern:

```bash
python3 -m timeit -n 5 -r 3 "from src.indexer import load_index; load_index('data/index.json')"
```

## Video Demonstration Checklist

- Show all four required commands running successfully
- Demonstrate multi-word and phrase queries
- Show handling of empty or unknown queries
- Run the automated tests
- Show the Git history with incremental commits and feature branches
- Explain the crawler, indexer, and ranking decisions
- Reflect critically on GenAI use, verification, and debugging

## GenAI Declaration Reminder

This coursework is Green-category AI use. If AI tools were used during development, declare them clearly in the video and explain:

- where they helped
- where they were wrong or incomplete
- how outputs were verified
- what was learned by debugging or correcting them

## Dependencies

- Python 3.12
- `requests`
- `beautifulsoup4`
- `pytest`
- `pytest-cov`
- `ruff`
- `mypy`
