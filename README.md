# Trader

A social media sentiment collector for financial analysis.

## Sentiment Collector

The sentiment collector module fetches posts from social media platforms, analyzes them using LLM, and stores the results in a local SQLite database.

### Architecture

```
main.py (CLI entry point)
    |
    v
collectors/reddit.py --> models.py (Post dataclass)
    |                         |
    v                         v
llm.py (LangChain OpenAI) --> db.py (SQLite/Peewee)
    |                         |
    v                         v
config.py (centralized configuration)
```

### Features

- **Reddit Collection**: Fetches posts from subreddits (wallstreetbets, stocks, investing) - **No API key required**
- **Time Window Filtering**: Collect posts from the last N hours (default: 24)
- **LLM Sentiment Analysis**: Uses OpenAI GPT-4o-mini for sentiment classification (bullish/bearish/neutral)
- **Ticker Extraction**: Automatically extracts stock ticker symbols from posts
- **Content Deduplication**: SHA-256 hash-based deduplication before LLM calls
- **Controlled Concurrency**: Parallel LLM calls with semaphore (default: 8 concurrent)
- **Rule-based Prefiltering**: Skips ads, short content, and link-only posts before LLM
- **Performance Monitoring**: Tracks LLM latency and failure rates

### Installation

```bash
pip install -r requirements.txt
```

### Configuration

Set the following environment variables:

```bash
# Required for LLM analysis
export OPENAI_API_KEY=sk-your-api-key

# Optional configuration
export OPENAI_MODEL=gpt-4o-mini  # default
export MAX_PARALLEL_LLM=8        # default
export LOG_LEVEL=INFO            # default
```

**Note**: Reddit collection does not require API credentials. It uses public .json endpoints.

### Usage

```bash
# Test Reddit collector first (no API key needed)
python tests/test_collector.py

# Or test collector directly
python -m collectors.reddit --hours 1

# Run full pipeline (requires OPENAI_API_KEY)
python main.py --hours 6

# Test LLM analysis directly
python -m llm "AAPL earnings beat expectations, stock surging"
```

### Output

The collector prints a summary after each run:

```
Summary:
  reddit: collected=150, dedupe_skipped=10, analyzed=140, saved=85
  total: collected=150, saved=85
Perf:
  avg_latency_s=1.5, total_wall_time_s=45.2, attempts=140, failure_ratio=0.02
```

### Database Schema

Posts are stored in `sentiment.db` (SQLite) with the following fields:

| Field | Type | Description |
|-------|------|-------------|
| id | INTEGER | Primary key |
| source | VARCHAR | Data source (e.g., "reddit") |
| source_id | VARCHAR | Original post ID |
| source_url | VARCHAR | Link to original post |
| content | TEXT | Post content (title + body) |
| content_hash | VARCHAR | SHA-256 hash (unique index) |
| sentiment | VARCHAR | bullish / bearish / neutral |
| tickers | JSON | List of stock symbols |
| summary | TEXT | One-sentence LLM summary |
| author_id | VARCHAR | Author identifier |
| author_name | VARCHAR | Author display name |
| post_time | INTEGER | Unix timestamp of post |
| likes | INTEGER | Upvotes/likes count |
| comments | INTEGER | Comment count |
| shares | INTEGER | Share count |
| created_at | INTEGER | Record insertion timestamp |

### Module Reference

- `main.py` - CLI entry point and pipeline orchestration
- `collectors/reddit.py` - Reddit data collection (no API key required)
- `models.py` - Post dataclass with content_hash property
- `llm.py` - LangChain OpenAI sentiment analysis
- `db.py` - SQLite/Peewee database operations
- `config.py` - Centralized configuration and performance monitoring
- `tests/test_collector.py` - Collector test suite

v1数据框架：先加载target.txt中的所有关注的index的数据（包括1年内的天级数据+以当前时间戳往前推24小时的15min数据，如果没有提取时间戳等工具自行添加） 储存在sentiment.db中 并运行@main.py 加载sentiment数据（以当天时间戳向前推24小时社交媒体上post的） 也储存在sentiment.db中
