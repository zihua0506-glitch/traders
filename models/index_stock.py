"""Index stock ORM model and helpers."""

from __future__ import annotations

from datetime import datetime
from typing import List

from peewee import AutoField, CharField, IntegerField, IntegrityError

from .base import BaseModel


class IndexStock(BaseModel):
    """Table storing index component stocks (S&P 500, Nasdaq 100)."""

    id = AutoField()

    ticker = CharField(max_length=16, unique=True, index=True)
    company_name = CharField(max_length=256)
    index_name = CharField(max_length=32)  # sp500, nasdaq100

    sector = CharField(max_length=128, null=True)
    industry = CharField(max_length=256, null=True)

    updated_at = IntegerField()  # Unix timestamp


def save_index_stock(
    ticker: str,
    company_name: str,
    index_name: str,
    sector: str | None = None,
    industry: str | None = None,
) -> bool:
    """Save or update an index stock record.

    Uses ticker as unique key. Updates existing record if ticker exists.
    Returns True on success.
    """
    now_ts = int(datetime.utcnow().timestamp())

    updated = (
        IndexStock.update(
            company_name=company_name,
            index_name=index_name,
            sector=sector,
            industry=industry,
            updated_at=now_ts,
        )
        .where(IndexStock.ticker == ticker)
        .execute()
    )

    if updated:
        return True

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


def get_index_stocks(index_name: str | None = None) -> List[IndexStock]:
    """Get all stocks, optionally filtered by index name."""
    query = IndexStock.select()
    if index_name:
        query = query.where(IndexStock.index_name == index_name)
    return list(query.order_by(IndexStock.ticker))


__all__ = ["IndexStock", "save_index_stock", "get_index_stocks"]

