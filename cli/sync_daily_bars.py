"""CLI: sync stock price bars (daily and/or intraday) for IndexStock tickers."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import configure_logging
from collectors.yahoo import sync_stock_price_bars
from db import get_index_stocks


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync adjusted stock price bars from Yahoo for tickers in IndexStock."
    )
    parser.add_argument(
        "--index",
        choices=["all", "sp500", "nasdaq100"],
        default="all",
        help="Which index membership to sync (default: all).",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--daily-only",
        action="store_true",
        help="Sync daily bars only (interval=1d).",
    )
    mode.add_argument(
        "--intraday-only",
        action="store_true",
        help="Sync intraday bars only (minute intervals with fallback).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of tickers (0 means no limit).",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.2,
        help="Sleep seconds between symbols (default: 0.2).",
    )
    return parser.parse_args()


def main() -> int:
    configure_logging()

    args = _parse_args()

    index_filter = None if args.index == "all" else args.index
    tickers = [row.ticker for row in get_index_stocks(index_filter)]
    if not tickers:
        print("No IndexStock tickers found in DB. Run `python3 cli/update_index_stocks.py` first.")
        return 1

    if args.limit and args.limit > 0:
        tickers = tickers[: args.limit]

    sync_daily = not args.intraday_only
    sync_intraday = not args.daily_only

    print("=" * 60)
    print("Stock Price Bars Sync (Yahoo)")
    print("=" * 60)
    print(f"Tickers: {len(tickers)} (index={args.index})")
    print(f"Sync: daily={sync_daily} intraday={sync_intraday}")
    print("-" * 60)

    totals = {
        "symbols": 0,
        "daily_inserted": 0,
        "daily_updated": 0,
        "daily_unchanged": 0,
        "daily_errors": 0,
        "intraday_inserted": 0,
        "intraday_updated": 0,
        "intraday_unchanged": 0,
        "intraday_errors": 0,
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

            if args.sleep and args.sleep > 0:
                time.sleep(args.sleep)
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


if __name__ == "__main__":
    raise SystemExit(main())
