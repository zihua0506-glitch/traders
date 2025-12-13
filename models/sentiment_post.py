"""Sentiment post ORM model and helpers.

Contains `SentimentPost` Peewee model and the `SentimentModel` facade
with helper functions used by collectors and LLM integration.
"""

from __future__ import annotations

from typing import List
from datetime import datetime

from peewee import (
    AutoField,
    CharField,
    IntegerField,
    TextField,
    IntegrityError,
)
from playhouse.sqlite_ext import JSONField

from .base import BaseModel, db
from .post import Post


class SentimentPost(BaseModel):
    """Table storing processed social posts with sentiment analysis."""

    id = AutoField()

    # Source metadata
    source = CharField(max_length=64)
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


def ensure_sentiment_indexes() -> None:
    """Create a unique index on `source_id` if it does not exist."""
    table_name = SentimentPost._meta.table_name
    idx_name = f"{table_name}_source_id_uniq"
    db.execute_sql(
        f"CREATE UNIQUE INDEX IF NOT EXISTS {idx_name} ON {table_name} (source_id)"
    )


def _get_table_columns(table_name: str) -> set:
    rows = db.execute_sql(f"PRAGMA table_info({table_name})").fetchall()
    return {row[1] for row in rows}


def ensure_sentiment_columns() -> None:
    """Ensure new columns exist on SentimentPost for extended metadata."""
    table = SentimentPost._meta.table_name
    cols = _get_table_columns(table)

    def add(col: str, ddl: str):
        if col not in cols:
            db.execute_sql(f"ALTER TABLE {table} ADD COLUMN {ddl}")

    add("bookmarks", "bookmarks INTEGER DEFAULT 0")
    add("views", "views INTEGER DEFAULT 0")
    add("images", "images TEXT DEFAULT '[]'")
    add("video_url", "video_url TEXT DEFAULT ''")
    add("quoted_url", "quoted_url TEXT DEFAULT ''")
    add("is_retweet", "is_retweet INTEGER DEFAULT 0")
    add("is_reply", "is_reply INTEGER DEFAULT 0")
    add("original_source_id", "original_source_id TEXT DEFAULT ''")


class SentimentModel:
    """DB storage facade for sentiment posts."""

    @staticmethod
    def save(post: Post, sentiment: str, tickers: List[str], summary: str) -> bool:
        if not post.content or not post.source or not post.source_url:
            raise ValueError("Post has missing required fields: content/source/source_url")
        if not isinstance(tickers, list):
            raise TypeError("tickers must be a list of strings")

        now_ts = int(datetime.utcnow().timestamp())
        row = {
            "source": post.source,
            "source_id": post.source_id,
            "source_url": post.source_url,
            "content": post.content,
            "content_hash": post.content_hash,
            "sentiment": sentiment,
            "tickers": tickers,
            "summary": summary,
            "author_id": post.author_id,
            "author_name": post.author_name,
            "post_time": post.post_time,
            "likes": post.likes,
            "comments": post.comments,
            "shares": post.shares,
            "bookmarks": getattr(post, "bookmarks", 0) or 0,
            "views": getattr(post, "views", 0) or 0,
            "images": getattr(post, "images", None) or [],
            "video_url": getattr(post, "video_url", "") or "",
            "quoted_url": getattr(post, "quoted_url", "") or "",
            "is_retweet": 1 if getattr(post, "is_retweet", False) else 0,
            "is_reply": 1 if getattr(post, "is_reply", False) else 0,
            "original_source_id": getattr(post, "original_source_id", "") or "",
            "created_at": now_ts,
        }

        try:
            cols = _get_table_columns(SentimentPost._meta.table_name)
            filtered = {k: v for k, v in row.items() if k in cols}
            SentimentPost.create(**filtered)
            return True
        except IntegrityError:
            return False

    @staticmethod
    def exists_content_hash(content_hash: str) -> bool:
        if not content_hash:
            return False
        return SentimentPost.select().where(SentimentPost.content_hash == content_hash).exists()

    @staticmethod
    def exists_source_id(source: str, source_id: str) -> bool:
        if not source or not source_id:
            return False
        return (
            SentimentPost.select()
            .where((SentimentPost.source == source) & (SentimentPost.source_id == source_id))
        ).exists()


def validate_fields_integrity(limit: int = 10) -> bool:
    """Check that sampled rows have non-empty sentiment/tickers/summary."""
    q = SentimentPost.select().order_by(SentimentPost.id.desc()).limit(limit)

    for row in q:
        if not row.sentiment or row.sentiment not in {"bullish", "bearish", "neutral"}:
            return False
        if row.tickers is None or not isinstance(row.tickers, list):
            return False
        if not row.summary:
            return False

    return True


def exists_content_hash(content_hash: str) -> bool:
    """Module-level helper delegating to SentimentModel.exists_content_hash."""
    return SentimentModel.exists_content_hash(content_hash)


__all__ = [
    "SentimentPost",
    "SentimentModel",
    "exists_content_hash",
    "validate_fields_integrity",
    "ensure_sentiment_indexes",
    "ensure_sentiment_columns",
]
