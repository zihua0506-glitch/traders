"""Database compatibility module.

This file remains as a thin shim to preserve imports like `from db import ...`.
It delegates to the new `models/` package where the base DB connection and
business ORM models live.
"""

from __future__ import annotations

from typing import List

from models.base import db, BaseModel
from models.index_stock import IndexStock, save_index_stock, get_index_stocks
from models.stock_price_bar import StockPriceBar, ensure_stock_price_bar_columns
from models.x_username import XUsername, get_enabled_x_usernames
from models.sentiment_post import (
    SentimentPost,
    SentimentModel,
    exists_content_hash,
    validate_fields_integrity,
    ensure_sentiment_columns,
    ensure_sentiment_indexes,
)
from models.post import Post


def init_db() -> None:
    """Initialize database and create tables if missing."""
    db.connect(reuse_if_open=True)
    db.create_tables([IndexStock, SentimentPost, StockPriceBar, XUsername])
    try:
        ensure_sentiment_columns()
    except Exception:
        pass
    try:
        ensure_stock_price_bar_columns()
    except Exception:
        pass
    try:
        ensure_sentiment_indexes()
    except Exception:
        pass


def save_post(post: Post, sentiment: str, tickers: List[str], summary: str) -> bool:
    """Persist a post (legacy helper). Delegates to SentimentModel.save."""
    return SentimentModel.save(post, sentiment, tickers, summary)


# Initialize on import for convenience in the MVP.
init_db()


__all__ = [
    "db",
    "BaseModel",
    "IndexStock",
    "SentimentPost",
    "StockPriceBar",
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
