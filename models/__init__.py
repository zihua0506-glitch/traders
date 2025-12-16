"""Application models package.

Exports core dataclass `Post` and Peewee ORM models used by the app.
This package organizes business models into focused modules and keeps
database connection logic in `models.base`.
"""

from .post import Post
from .base import db, BaseModel
from .index_stock import IndexStock, save_index_stock, get_index_stocks
from .sentiment_post import (
    SentimentPost,
    SentimentModel,
    exists_content_hash,
    validate_fields_integrity,
    ensure_sentiment_indexes,
    ensure_sentiment_columns,
)
from .stock_price_bar import StockPriceBar
from .x_username import XUsername, get_enabled_x_usernames

__all__ = [
    # Dataclass
    "Post",
    # DB core
    "db",
    "BaseModel",
    # Business models
    "IndexStock",
    "SentimentPost",
    "StockPriceBar",
    "XUsername",
    # Helpers
    "save_index_stock",
    "get_index_stocks",
    "SentimentModel",
    "exists_content_hash",
    "validate_fields_integrity",
    "get_enabled_x_usernames",
    # Ensure functions
    "ensure_sentiment_indexes",
    "ensure_sentiment_columns",
]
