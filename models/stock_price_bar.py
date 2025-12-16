"""Stock price bar ORM model and helpers."""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, Optional

from peewee import AutoField, CharField, FloatField, IntegerField, fn

from .base import BaseModel

logger = logging.getLogger(__name__)


def _normalize_symbol(symbol: str) -> str:
    return (symbol or "").strip().upper()


def _normalize_interval(interval: str) -> str:
    return (interval or "").strip()


def _normalize_session(session: str | None) -> str:
    value = (session or "").strip().lower()
    return value or "unknown"


def _normalize_float(value: Any) -> float:
    try:
        return round(float(value), 10)
    except Exception:
        return 0.0


def _normalize_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


class StockPriceBar(BaseModel):
    """Table storing stock price bars (daily and intraday)."""

    id = AutoField()

    symbol = CharField(max_length=32, index=True)
    interval = CharField(max_length=8, index=True)
    ts = IntegerField(index=True)  # UTC unix seconds

    open = FloatField()
    high = FloatField()
    low = FloatField()
    close = FloatField()
    volume = IntegerField(default=0)
    session = CharField(max_length=16, default="unknown")  # regular | extended | unknown

    class Meta:
        table_name = "stock_price_bars"
        indexes = (
            (("symbol", "interval", "ts"), True),
        )

    @classmethod
    def get_latest_ts(cls, symbol: str, interval: str) -> Optional[int]:
        symbol = _normalize_symbol(symbol)
        interval = _normalize_interval(interval)
        if not symbol or not interval:
            return None

        row = (
            cls.select(fn.MAX(cls.ts).alias("max_ts"))
            .where((cls.symbol == symbol) & (cls.interval == interval))
            .dicts()
            .get_or_none()
        )
        if not row:
            return None
        max_ts = row.get("max_ts")
        return int(max_ts) if max_ts is not None else None

    @classmethod
    def save_bar(
        cls,
        *,
        symbol: str,
        interval: str,
        ts: int,
        open_price: Any,
        high: Any,
        low: Any,
        close: Any,
        volume: Any,
        session: str | None,
    ) -> str:
        symbol_n = _normalize_symbol(symbol)
        interval_n = _normalize_interval(interval)
        if not symbol_n or not interval_n:
            raise ValueError("symbol and interval are required")

        defaults: Dict[str, Any] = {
            "open": _normalize_float(open_price),
            "high": _normalize_float(high),
            "low": _normalize_float(low),
            "close": _normalize_float(close),
            "volume": _normalize_int(volume),
            "session": _normalize_session(session),
        }

        bar, created = cls.get_or_create(
            symbol=symbol_n,
            interval=interval_n,
            ts=int(ts),
            defaults=defaults,
        )
        if created:
            return "inserted"

        changed = False
        for field, value in defaults.items():
            if getattr(bar, field) != value:
                setattr(bar, field, value)
                changed = True

        if changed:
            bar.save()
            return "updated"

        return "unchanged"

    @classmethod
    def save_bars(cls, rows: Iterable[Dict[str, Any]]) -> Dict[str, int]:
        stats = {"inserted": 0, "updated": 0, "unchanged": 0, "errors": 0}
        database = cls._meta.database

        with database.atomic():
            for row in rows:
                try:
                    result = cls.save_bar(
                        symbol=str(row.get("symbol", "")),
                        interval=str(row.get("interval", "")),
                        ts=int(row.get("ts", 0)),
                        open_price=row.get("open"),
                        high=row.get("high"),
                        low=row.get("low"),
                        close=row.get("close"),
                        volume=row.get("volume", 0),
                        session=row.get("session"),
                    )
                    if result in stats:
                        stats[result] += 1
                    else:
                        stats["errors"] += 1
                except Exception as exc:
                    stats["errors"] += 1
                    logger.warning("[stock_price_bars] save failed: %s", exc, exc_info=True)

        return stats


__all__ = ["StockPriceBar"]
