# Trader

A multi-source sentiment intelligence pipeline for financial markets. Collects posts from Reddit, Yahoo Finance, and Finviz, analyzes sentiment via LLM, and stores structured results in a local SQLite database for downstream trading signal research.

## Features

- **Multi-source collection** — Reddit (configurable subreddits), Yahoo Finance, Finviz news feeds
- **LLM sentiment analysis** — parallel LLM calls with configurable concurrency for throughput
- **Deduplication** — content-hash based deduplication prevents re-processing seen posts
- **CLI interface** — run collection, analysis, and sync from the command line
- **Browser automation** — integrates with [browser-use CLI](https://docs.browser-use.com/open-source/browser-use-cli) for richer data collection
- **Performance sampling** — built-in latency tracking for LLM calls and pipeline throughput

## Quickstart

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

Install browser-use CLI separately:

```
https://docs.browser-use.com/open-source/browser-use-cli
```

### 2. Configure data sources

**`subreddits.json`** — list of subreddit names to monitor

**`x_user_id.json`** — X (Twitter) user IDs for collection

### 3. Run

```bash
# Collect and analyze the last 24 hours
python main.py

# Custom time window
python main.py --hours 48

# Run the swing-scout skill
skill swing-scout
```

Or use the sync-and-run wrapper:

```bash
python sync_and_run.py
```

## Project Structure

```
trader/
├── collectors/      # Source-specific scrapers (Reddit, Yahoo, Finviz)
├── models/          # Data models (Post, etc.)
├── cli/             # CLI commands
├── tools/           # Utility tools
├── tests/           # Test suite
├── main.py          # Pipeline entrypoint
├── db.py            # SQLite persistence layer
├── llm.py           # LLM sentiment analysis
├── config.py        # Centralized config (logging, constants, env vars)
└── sync_and_run.py  # Sync + run wrapper
```

## Configuration

Set environment variables or use a `.env` file:

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | API key for LLM calls |
| `LOG_LEVEL` | Logging verbosity (`INFO`, `DEBUG`, etc.) |

## Requirements

See [requirements.txt](requirements.txt) for the full dependency list.
