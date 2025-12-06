"""SQLite + Peewee database module for sentiment posts.

Defines the `SentimentPost` table and helper functions:
- `save_post(post, sentiment, tickers, summary)` inserts with unique
  `content_hash` and returns True on success or False on unique conflicts.
- `exists_content_hash(content_hash)` for pre-dedupe checks.
- `validate_fields_integrity(limit)` to assert non-empty `sentiment/tickers/summary`.

This module uses `playhouse.sqlite_ext.SqliteExtDatabase` so we can store
JSON via `JSONField` in SQLite (backed by the JSON1 extension where available).
"""

from __future__ import annotations

from typing import List
from datetime import datetime

from peewee import (
    AutoField,
    CharField,
    FloatField,
    IntegerField,
    TextField,
    IntegrityError,
    Model,
)
from playhouse.sqlite_ext import JSONField, SqliteExtDatabase

from models import Post


# Database file in the project root; simple and portable for MVP.
DB_FILE = "sentiment.db"
db = SqliteExtDatabase(DB_FILE, pragmas={
    "journal_mode": "wal",
    "cache_size": -1024 * 64,  # 64MB page cache
    "foreign_keys": 1,
    "ignore_check_constraints": 0,
})


class BaseModel(Model):
    class Meta:
        database = db


class IndexStock(BaseModel):
    """Table storing index component stocks (S&P 500, Nasdaq 100)."""

    # Primary key
    id = AutoField()

    # Stock identifiers
    ticker = CharField(max_length=16, unique=True, index=True)
    company_name = CharField(max_length=256)

    # Index membership
    index_name = CharField(max_length=32)  # sp500, nasdaq100

    # Sector/Industry classification
    sector = CharField(max_length=128, null=True)
    industry = CharField(max_length=256, null=True)

    # Metadata
    updated_at = IntegerField()  # Unix timestamp


class SentimentPost(BaseModel):
    """Table storing processed social posts with sentiment analysis."""

    # Primary key
    id = AutoField()

    # Source metadata
    source = CharField(max_length=64)
    source_id = CharField(max_length=128)
    source_url = CharField(max_length=512)

    # Content and dedupe hash
    content = TextField()
    content_hash = CharField(max_length=64, unique=True, index=True)

    # LLM outputs
    sentiment = CharField(max_length=16)  # bullish | bearish | neutral
    tickers = JSONField()  # list of ticker strings
    summary = TextField()

    # Author and timing
    author_id = CharField(max_length=128)
    author_name = CharField(max_length=128)
    post_time = IntegerField()  # unix seconds

    # Engagement metrics
    likes = IntegerField(default=0)
    comments = IntegerField(default=0)
    shares = IntegerField(default=0)

    # Insert timestamp
    created_at = IntegerField()  # unix seconds


def init_db() -> None:
    """Initialize database and create tables if missing."""
    db.connect(reuse_if_open=True)
    db.create_tables([IndexStock, SentimentPost])


def save_post(post: Post, sentiment: str, tickers: List[str], summary: str) -> bool:
    """Persist a post with sentiment results.

    Returns False if a row with the same `content_hash` already exists
    (unique constraint violation). Returns True on successful insert.
    """
    # Basic defensive checks for required fields
    if not post.content or not post.source or not post.source_url:
        raise ValueError("Post has missing required fields: content/source/source_url")
    if not isinstance(tickers, list):
        raise TypeError("tickers must be a list of strings")

    now_ts = int(datetime.utcnow().timestamp())

    try:
        SentimentPost.create(
            source=post.source,
            source_id=post.source_id,
            source_url=post.source_url,
            content=post.content,
            content_hash=post.content_hash,
            sentiment=sentiment,
            tickers=tickers,
            summary=summary,
            author_id=post.author_id,
            author_name=post.author_name,
            post_time=post.post_time,
            likes=post.likes,
            comments=post.comments,
            shares=post.shares,
            created_at=now_ts,
        )
        return True
    except IntegrityError:
        # Duplicate content_hash is considered a normal dedupe case
        return False


def exists_content_hash(content_hash: str) -> bool:
    """Return True if a row with the given content_hash exists."""
    if not content_hash:
        return False
    return SentimentPost.select().where(
        SentimentPost.content_hash == content_hash
    ).exists()


def validate_fields_integrity(limit: int = 10) -> bool:
    """Check that sampled rows have non-empty sentiment/tickers/summary.

    Returns True if all sampled rows pass basic validation; otherwise False.
    """
    q = (SentimentPost
         .select()
         .order_by(SentimentPost.id.desc())
         .limit(limit))

    for row in q:
        if not row.sentiment or row.sentiment not in {"bullish", "bearish", "neutral"}:
            return False
        # `tickers` is expected to be a list (possibly empty list)
        if row.tickers is None or not isinstance(row.tickers, list):
            return False
        if not row.summary:
            return False

    return True


# Initialize on import for convenience in the MVP.
init_db()


def save_index_stock(
    ticker: str,
    company_name: str,
    index_name: str,
    sector: str = None,
    industry: str = None,
) -> bool:
    """Save or update an index stock record.

    Uses ticker as unique key. Updates existing record if ticker exists.
    Returns True on success.
    """
    now_ts = int(datetime.utcnow().timestamp())

    # Try to update existing record first
    updated = IndexStock.update(
        company_name=company_name,
        index_name=index_name,
        sector=sector,
        industry=industry,
        updated_at=now_ts,
    ).where(IndexStock.ticker == ticker).execute()

    if updated:
        return True

    # Insert new record
    try:
        IndexStock.create(
            ticker=ticker,
            company_name=company_name,
            index_name=index_name,
            sector=sector,
            industry=industry,
            updated_at=now_ts,
        )
        return True
    except IntegrityError:
        return False


def get_index_stocks(index_name: str = None) -> List[IndexStock]:
    """Get all stocks, optionally filtered by index name."""
    query = IndexStock.select()
    if index_name:
        query = query.where(IndexStock.index_name == index_name)
    return list(query.order_by(IndexStock.ticker))


__all__ = [
    "db",
    "IndexStock",
    "SentimentPost",
    "init_db",
    "save_index_stock",
    "get_index_stocks",
    "save_post",
    "exists_content_hash",
    "validate_fields_integrity",
]
