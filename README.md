# COMP3011 Coursework 2: Search Engine Tool

Python search tool for crawling `https://quotes.toscrape.com/`, building an inverted index, and searching the indexed pages from the command line.

## Status

Bootstrap in progress. The project structure, CI, and TDD workflow are being set up first.

## Planned Structure

```text
repository-name/
├── src/
│   ├── crawler.py
│   ├── indexer.py
│   ├── search.py
│   └── main.py
├── tests/
│   ├── test_crawler.py
│   ├── test_indexer.py
│   └── test_search.py
├── data/
├── requirements.txt
└── README.md
```

## Development

```bash
python3 -m pip install -r requirements-dev.txt
pytest
```

