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
    BooleanField,
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
    # Keep model field non-unique to avoid migration-time crashes on existing data.
    # We still enforce uniqueness via a runtime-created DB index in `ensure_db_indexes()`.
    source_id = CharField(max_length=128, index=True)
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

    # Extended media and relation fields
    bookmarks = IntegerField(default=0)
    views = IntegerField(default=0)
    images = JSONField(null=True)  # list[str]
    video_url = CharField(max_length=512, default="")
    quoted_url = CharField(max_length=512, default="")
    is_retweet = IntegerField(default=0)  # 0/1
    is_reply = IntegerField(default=0)   # 0/1
    original_source_id = CharField(max_length=128, default="")

    # Insert timestamp
    created_at = IntegerField()  # unix seconds

    class Meta:
        indexes = (
            (("source", "source_id"), True),  # unique composite index
        )


class XUsername(BaseModel):
    """Table storing X (Twitter) usernames to collect."""

    id = AutoField()
    username = CharField(max_length=64, unique=True, index=True)
    enabled = BooleanField(default=True)


def init_db() -> None:
    """Initialize database and create tables if missing."""
    db.connect(reuse_if_open=True)
    db.create_tables([IndexStock, SentimentPost, XUsername])
    # Ensure additional indexes beyond Peewee's table creation
    try:
        ensure_db_indexes()
    except Exception:
        # Avoid crashing on index creation (e.g., duplicates present); keep MVP resilient
        pass

def ensure_db_indexes() -> None:
    """Create a unique index on `source_id` if it does not exist.

    Peewee won't auto-migrate existing tables for field changes. This helper
    creates the unique index at runtime for SQLite.
    """
    table_name = SentimentPost._meta.table_name
    idx_name = f"{table_name}_source_id_uniq"
    # SQLite supports IF NOT EXISTS for CREATE INDEX
    db.execute_sql(
        f"CREATE UNIQUE INDEX IF NOT EXISTS {idx_name} ON {table_name} (source_id)"
    )


def save_post(post: Post, sentiment: str, tickers: List[str], summary: str) -> bool:
    """Persist a post (legacy helper). Delegates to SentimentModel.save."""
    return SentimentModel.save(post, sentiment, tickers, summary)


def exists_content_hash(content_hash: str) -> bool:
    """Legacy helper; delegates to SentimentModel.exists_content_hash."""
    return SentimentModel.exists_content_hash(content_hash)


class SentimentModel:
    """DB storage facade for sentiment posts."""

    @staticmethod
    def save(post: Post, sentiment: str, tickers: List[str], summary: str) -> bool:
        """Save a post row with sentiment fields.

        Returns False on unique conflicts (content_hash or source+source_id), True on success.
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
                bookmarks=getattr(post, "bookmarks", 0) or 0,
                views=getattr(post, "views", 0) or 0,
                images=getattr(post, "images", None) or [],
                video_url=getattr(post, "video_url", "") or "",
                quoted_url=getattr(post, "quoted_url", "") or "",
                is_retweet=1 if getattr(post, "is_retweet", False) else 0,
                is_reply=1 if getattr(post, "is_reply", False) else 0,
                original_source_id=getattr(post, "original_source_id", "") or "",
                created_at=now_ts,
            )
            return True
        except IntegrityError:
            return False

    @staticmethod
    def exists_content_hash(content_hash: str) -> bool:
        """Return True if content_hash exists."""
        if not content_hash:
            return False
        return SentimentPost.select().where(SentimentPost.content_hash == content_hash).exists()

    @staticmethod
    def exists_source_id(source: str, source_id: str) -> bool:
        """Return True if (source, source_id) combo exists."""
        if not source or not source_id:
            return False
        return (SentimentPost
                .select()
                .where((SentimentPost.source == source) & (SentimentPost.source_id == source_id))
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


def get_enabled_x_usernames() -> List[str]:
    """Return all enabled X usernames (enabled = True)."""
    q = (XUsername
         .select(XUsername.username)
         .where(XUsername.enabled == True)  # noqa: E712
         .order_by(XUsername.username))
    return [row.username for row in q]


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
    "XUsername",
    "init_db",
    "save_index_stock",
    "get_index_stocks",
    "save_post",
    "exists_content_hash",
    "validate_fields_integrity",
    "SentimentModel",
    "get_enabled_x_usernames",
]
