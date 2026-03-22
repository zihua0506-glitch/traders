"""CLI: stock data operations – sync, query daily bars, query minute bars."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import configure_logging
from collectors.yahoo import sync_stock_price_bars
from db import get_index_stocks
from models import StockPriceBar


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def _query_daily(symbols: list[str], days: int) -> dict:
    result = {}
    for sym in symbols:
        rows = (
            StockPriceBar.select()
            .where(
                (StockPriceBar.symbol == sym.upper())
                & (StockPriceBar.interval == "1d")
            )
            .order_by(StockPriceBar.ts.desc())
            .limit(days)
        )
        result[sym.upper()] = [
            {
                "ts": r.ts,
                "trade_day": r.trade_day,
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "volume": r.volume,
            }
            for r in rows
        ]
    return result


def _query_minute(symbols: list[str], minutes: int) -> dict:
    minute_intervals = {"1m", "2m", "5m", "15m", "30m", "60m"}
    result = {}
    for sym in symbols:
        rows = (
            StockPriceBar.select()
            .where(
                (StockPriceBar.symbol == sym.upper())
                & (StockPriceBar.interval.in_(minute_intervals))
            )
            .order_by(StockPriceBar.ts.desc())
            .limit(minutes)
        )
        result[sym.upper()] = [
            {
                "ts": r.ts,
                "trade_day": r.trade_day,
                "interval": r.interval,
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "volume": r.volume,
            }
            for r in rows
        ]
    return result


# ---------------------------------------------------------------------------
# Sync logic (preserved from sync_daily_bars.py)
# ---------------------------------------------------------------------------

def _run_sync(tickers: list[str], sync_daily: bool, sync_intraday: bool, sleep: float) -> int:
    print("=" * 60)
    print("Stock Price Bars Sync (Yahoo)")
    print("=" * 60)
    print(f"Tickers: {len(tickers)} ({', '.join(tickers)})")
    print(f"Sync: daily={sync_daily} intraday={sync_intraday}")
    print("-" * 60)

    totals = {
        "symbols": 0,
        "daily_inserted": 0, "daily_updated": 0, "daily_unchanged": 0, "daily_errors": 0,
        "intraday_inserted": 0, "intraday_updated": 0, "intraday_unchanged": 0, "intraday_errors": 0,
    }

    for i, ticker in enumerate(tickers, 1):
        try:
            out = sync_stock_price_bars(ticker, sync_daily=sync_daily, sync_intraday=sync_intraday)
            totals["symbols"] += 1

            daily = out.get("daily", {}) or {}
            intraday = out.get("intraday", {}) or {}

            if sync_daily:
                totals["daily_inserted"] += int(daily.get("inserted", 0))
                totals["daily_updated"] += int(daily.get("updated", 0))
                totals["daily_unchanged"] += int(daily.get("unchanged", 0))
                totals["daily_errors"] += int(daily.get("errors", 0))

            if sync_intraday:
                totals["intraday_inserted"] += int(intraday.get("inserted", 0))
                totals["intraday_updated"] += int(intraday.get("updated", 0))
                totals["intraday_unchanged"] += int(intraday.get("unchanged", 0))
                totals["intraday_errors"] += int(intraday.get("errors", 0))

            parts = [f"[{i}/{len(tickers)}] {ticker}"]
            if sync_daily:
                parts.append(
                    "daily "
                    f"ins={int(daily.get('inserted', 0))} "
                    f"upd={int(daily.get('updated', 0))} "
                    f"same={int(daily.get('unchanged', 0))} "
                    f"err={int(daily.get('errors', 0))} "
                    f"range=({daily.get('start_ts')},{daily.get('end_ts')})"
                )
            if sync_intraday:
                parts.append(
                    f"intraday({intraday.get('interval')}) "
                    f"ins={int(intraday.get('inserted', 0))} "
                    f"upd={int(intraday.get('updated', 0))} "
                    f"same={int(intraday.get('unchanged', 0))} "
                    f"err={int(intraday.get('errors', 0))} "
                    f"range=({intraday.get('start_ts')},{intraday.get('end_ts')})"
                )
            print(" | ".join(parts))

            if sleep > 0:
                time.sleep(sleep)
        except KeyboardInterrupt:
            print("\nInterrupted.")
            break
        except Exception as exc:
            totals["daily_errors"] += 1 if sync_daily else 0
            totals["intraday_errors"] += 1 if sync_intraday else 0
            print(f"[{i}/{len(tickers)}] {ticker} failed: {exc}")
            continue

    print("-" * 60)
    print("Summary:")
    print(f"  symbols: {totals['symbols']}")
    if sync_daily:
        print(
            "  daily: "
            f"inserted={totals['daily_inserted']} "
            f"updated={totals['daily_updated']} "
            f"unchanged={totals['daily_unchanged']} "
            f"errors={totals['daily_errors']}"
        )
    if sync_intraday:
        print(
            "  intraday: "
            f"inserted={totals['intraday_inserted']} "
            f"updated={totals['intraday_updated']} "
            f"unchanged={totals['intraday_unchanged']} "
            f"errors={totals['intraday_errors']}"
        )
    print("=" * 60)

    return 0 if totals["symbols"] > 0 else 1


# ---------------------------------------------------------------------------
# Subcommand: sync
# ---------------------------------------------------------------------------

def _add_sync_parser(subparsers):
    p = subparsers.add_parser("sync", help="Sync stock price bars from Yahoo Finance.")
    p.add_argument("symbols", nargs="*", help="Ticker symbols (e.g. AAPL TSLA). If omitted, sync all IndexStock tickers.")
    p.add_argument("--index", choices=["all", "sp500", "nasdaq100"], default="all")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--daily-only", action="store_true")
    mode.add_argument("--intraday-only", action="store_true")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--sleep", type=float, default=0.2)
    return p


def _cmd_sync(args) -> int:
    if args.symbols:
        tickers = [s.upper() for s in args.symbols]
    else:
        index_filter = None if args.index == "all" else args.index
        tickers = [row.ticker for row in get_index_stocks(index_filter)]
        if not tickers:
            print("No IndexStock tickers found in DB. Run `python3 cli/update_index_stocks.py` first.")
            return 1

    if args.limit and args.limit > 0:
        tickers = tickers[: args.limit]

    sync_daily = not args.intraday_only
    sync_intraday = not args.daily_only
    return _run_sync(tickers, sync_daily, sync_intraday, args.sleep)


# ---------------------------------------------------------------------------
# Subcommand: daily
# ---------------------------------------------------------------------------

def _add_daily_parser(subparsers):
    p = subparsers.add_parser("daily", help="Sync and return recent daily bars as JSON.")
    p.add_argument("symbols", nargs="+", help="Ticker symbols (e.g. AAPL TSLA NVDA).")
    p.add_argument("--days", type=int, default=5, help="Number of trading days to return (default: 5).")
    return p


def _cmd_daily(args) -> int:
    tickers = [s.upper() for s in args.symbols]
    _run_sync(tickers, sync_daily=True, sync_intraday=False, sleep=0.2)
    data = _query_daily(tickers, args.days)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


# ---------------------------------------------------------------------------
# Subcommand: minute
# ---------------------------------------------------------------------------

def _add_minute_parser(subparsers):
    p = subparsers.add_parser("minute", help="Sync and return recent minute bars as JSON.")
    p.add_argument("symbols", nargs="+", help="Ticker symbols (e.g. AAPL TSLA NVDA).")
    p.add_argument("--minutes", type=int, default=60, help="Number of minutes to look back (default: 60).")
    return p


def _cmd_minute(args) -> int:
    tickers = [s.upper() for s in args.symbols]
    _run_sync(tickers, sync_daily=False, sync_intraday=True, sleep=0.2)
    data = _query_minute(tickers, args.minutes)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    configure_logging()

    parser = argparse.ArgumentParser(description="Stock data CLI: sync, query daily/minute bars.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    _add_sync_parser(subparsers)
    _add_daily_parser(subparsers)
    _add_minute_parser(subparsers)

    args = parser.parse_args()

    handlers = {
        "sync": _cmd_sync,
        "daily": _cmd_daily,
        "minute": _cmd_minute,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
