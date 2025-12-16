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


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _merge_index_names(existing: str | None, incoming: str) -> str:
    existing_names = {name.strip() for name in (existing or "").split(",") if name.strip()}
    incoming_names = {name.strip() for name in incoming.split(",") if name.strip()}

    order = {"sp500": 0, "nasdaq100": 1}
    merged = sorted(existing_names | incoming_names, key=lambda n: order.get(n, 99))
    return ",".join(merged)


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

    ticker = ticker.strip()
    company_name = company_name.strip()
    index_name = index_name.strip()
    sector = _normalize_optional_text(sector)
    industry = _normalize_optional_text(industry)

    existing = IndexStock.get_or_none(IndexStock.ticker == ticker)
    if existing is not None:
        existing.company_name = company_name or existing.company_name
        existing.index_name = _merge_index_names(existing.index_name, index_name)
        incoming_is_sp500 = "sp500" in {name.strip() for name in index_name.split(",")}
        if sector and (incoming_is_sp500 or not _normalize_optional_text(existing.sector)):
            existing.sector = sector
        if industry and (incoming_is_sp500 or not _normalize_optional_text(existing.industry)):
            existing.industry = industry
        existing.updated_at = now_ts
        existing.save()
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
        query = query.where(IndexStock.index_name.contains(index_name))
    return list(query.order_by(IndexStock.ticker))


__all__ = ["IndexStock", "save_index_stock", "get_index_stocks"]
