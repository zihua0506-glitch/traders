"""Unit tests for stock price bars model and helpers.

Run with: python tests/test_stock_price_bars.py
Or: python -m pytest tests/test_stock_price_bars.py -v
"""

import os
import sys
from pathlib import Path

import pandas as pd
from playhouse.sqlite_ext import SqliteExtDatabase

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import db as dbmod
from collectors.yahoo import _classify_trading_session
from models import StockPriceBar


def use_temp_db(path: str) -> None:
    """Rebind peewee models to a temporary SQLite database file."""
    newdb = SqliteExtDatabase(path, pragmas={
        "journal_mode": "wal",
        "cache_size": -1024 * 16,
        "foreign_keys": 1,
        "ignore_check_constraints": 0,
    })
    dbmod.db = newdb
    dbmod.BaseModel._meta.database = newdb
    dbmod.IndexStock._meta.database = newdb
    dbmod.SentimentPost._meta.database = newdb
    dbmod.StockPriceBar._meta.database = newdb
    dbmod.XUsername._meta.database = newdb


def test_stock_price_bar_upsert_and_latest_ts() -> bool:
    tmp_db = str(Path(__file__).parent / "test_stock_price_bars.db")
    try:
        os.remove(tmp_db)
    except Exception:
        pass

    use_temp_db(tmp_db)
    dbmod.init_db()

    symbol = "AAPL"
    interval = "1m"

    r1 = StockPriceBar.save_bar(
        symbol=symbol,
        interval=interval,
        ts=1000,
        open_price=10,
        high=11,
        low=9,
        close=10.5,
        volume=100,
        session="regular",
    )
    assert r1 == "inserted"

    r2 = StockPriceBar.save_bar(
        symbol=symbol,
        interval=interval,
        ts=1000,
        open_price=10,
        high=11,
        low=9,
        close=10.6,
        volume=101,
        session="extended",
    )
    assert r2 == "updated"

    bar = StockPriceBar.get_or_none(
        (StockPriceBar.symbol == symbol) & (StockPriceBar.interval == interval) & (StockPriceBar.ts == 1000)
    )
    assert bar is not None
    assert bar.close == 10.6
    assert bar.volume == 101
    assert bar.session == "extended"

    r3 = StockPriceBar.save_bar(
        symbol=symbol,
        interval=interval,
        ts=1000,
        open_price=10,
        high=11,
        low=9,
        close=10.6,
        volume=101,
        session="extended",
    )
    assert r3 == "unchanged"

    StockPriceBar.save_bar(
        symbol=symbol,
        interval=interval,
        ts=1010,
        open_price=10.6,
        high=11,
        low=10.5,
        close=10.8,
        volume=80,
        session="regular",
    )
    assert StockPriceBar.get_latest_ts(symbol, interval) == 1010
    return True


def test_trading_session_classification() -> bool:
    ts_utc = pd.Series(pd.to_datetime([
        "2025-01-02 14:30:00+00:00",  # 09:30 NY
        "2025-01-02 15:00:00+00:00",  # 10:00 NY
        "2025-01-02 13:00:00+00:00",  # 08:00 NY
        "2025-01-02 21:00:00+00:00",  # 16:00 NY
    ], utc=True))

    session = _classify_trading_session(ts_utc, "America/New_York").tolist()
    assert session == ["regular", "regular", "extended", "extended"]

    unknown = _classify_trading_session(ts_utc, None).tolist()
    assert unknown == ["unknown", "unknown", "unknown", "unknown"]
    return True


def run():
    print("Running stock_price_bars tests...")
    try:
        assert test_stock_price_bar_upsert_and_latest_ts()
        print("[PASS] test_stock_price_bar_upsert_and_latest_ts")
        assert test_trading_session_classification()
        print("[PASS] test_trading_session_classification")
        sys.exit(0)
    except AssertionError as e:
        print(f"[FAIL] {e}")
        sys.exit(1)


if __name__ == "__main__":
    run()

