"""Yahoo Finance news collector module.

Fetches financial news from Yahoo Finance RSS feeds and web pages.
"""

from __future__ import annotations

import hashlib
import logging
import time
import urllib3
from typing import List, Tuple, Optional, Dict, Any
from datetime import datetime, timezone, timedelta

from bs4 import BeautifulSoup

from models import Post, StockPriceBar
from .base import BaseCollector


# Suppress SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

# Yahoo Finance URLs
# Note: RSS feeds are heavily rate-limited (429), so we primarily use HTML scraping
QUOTE_URL = "https://finance.yahoo.com/quote/{symbol}/"
NEWS_PAGE_URL = "https://finance.yahoo.com/topic/stock-market-news/"


class YahooFinanceCollector(BaseCollector):
    """Yahoo Finance news collector.

    Fetches news from RSS feeds (preferred) or web scraping (fallback).
    """

    source_name = "yahoo"

    def __init__(self, timeout: int = 15, delay: float = 0.3):
        super().__init__(timeout=timeout, delay=delay)
        # Yahoo needs specific headers
        self.session.headers.update({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })

    def fetch_by_symbol(
        self,
        symbol: str,
        limit: int = 50,
        since_ts: int = 0,
    ) -> List[dict]:
        """Fetch news for a specific stock symbol.

        Args:
            symbol: Stock ticker symbol (e.g., "AAPL")
            limit: Maximum number of news items
            since_ts: Only return items after this timestamp

        Returns:
            List of raw news dictionaries
        """
        try:
            return self._fetch_quote_page(symbol, limit, since_ts)
        except Exception as e:
            logger.error("[yahoo] Failed to fetch %s: %s", symbol, e)
            return []

    def fetch_trending(
        self,
        limit: int = 50,
        since_ts: int = 0,
    ) -> List[dict]:
        """Fetch trending/latest news from Yahoo Finance.

        Args:
            limit: Maximum number of news items
            since_ts: Only return items after this timestamp

        Returns:
            List of raw news dictionaries
        """
        try:
            return self._fetch_news_page(limit, since_ts)
        except Exception as e:
            logger.error("[yahoo] Failed to fetch trending: %s", e)
            return []

    def _fetch_quote_page(
        self,
        symbol: str,
        limit: int,
        since_ts: int,
    ) -> List[dict]:
        """Fetch news from Yahoo Finance quote page.

        The quote page contains news in 'storyitem' sections.
        """
        url = QUOTE_URL.format(symbol=symbol.upper())

        try:
            response = self._get(url, verify=False)
            response.raise_for_status()
        except Exception as e:
            raise Exception(f"Quote page request failed: {e}")

        return self._parse_storyitems(response.text, symbol.upper(), limit, since_ts)

    def _fetch_news_page(
        self,
        limit: int,
        since_ts: int,
    ) -> List[dict]:
        """Fetch news from Yahoo Finance stock market news page."""
        try:
            response = self._get(NEWS_PAGE_URL, verify=False)
            response.raise_for_status()
        except Exception as e:
            raise Exception(f"News page request failed: {e}")

        return self._parse_storyitems(response.text, "", limit, since_ts)

    def _parse_storyitems(
        self,
        html: str,
        symbol: str,
        limit: int,
        since_ts: int,
    ) -> List[dict]:
        """Parse news from storyitem sections.

        Yahoo Finance uses <section data-testid="storyitem"> for news items.
        """
        soup = BeautifulSoup(html, "html.parser")
        stories = soup.find_all("section", {"data-testid": "storyitem"})

        news = []
        now = int(time.time())

        for story in stories:
            if len(news) >= limit:
                break

            # Find title in h3
            h3 = story.find("h3")
            title = h3.get_text().strip() if h3 else ""

            if not title or len(title) < 10:
                continue

            # Find link
            link = story.find("a", href=True)
            href = link.get("href", "") if link else ""
            if href and not href.startswith("http"):
                href = f"https://finance.yahoo.com{href}"

            # Find source and time (format: "Source - Xh ago")
            source = "Yahoo Finance"
            pub_time = now

            for div in story.find_all("div"):
                text = div.get_text().strip()
                if " ago" in text and chr(8226) in text:
                    parts = text.split(chr(8226))
                    if len(parts) >= 2:
                        source = parts[0].strip()
                        time_str = parts[1].strip()
                        pub_time = self._parse_relative_time(time_str, now)
                    break

            # Time filter
            if since_ts and pub_time < since_ts:
                continue

            news.append({
                "title": title,
                "link": href,
                "summary": "",
                "source": source,
                "published": pub_time,
                "_symbol": symbol,
            })

        return news

    def _parse_relative_time(self, time_str: str, now: int) -> int:
        """Parse relative time string to Unix timestamp.

        Formats: "1h ago", "2d ago", "30m ago", "yesterday"
        """
        time_str = time_str.lower().strip()

        try:
            if "h ago" in time_str:
                hours = int(time_str.replace("h ago", "").strip())
                return now - hours * 3600
            elif "m ago" in time_str:
                minutes = int(time_str.replace("m ago", "").strip())
                return now - minutes * 60
            elif "d ago" in time_str:
                days = int(time_str.replace("d ago", "").strip())
                return now - days * 86400
            elif "yesterday" in time_str:
                return now - 86400
            elif "just now" in time_str:
                return now
        except (ValueError, AttributeError):
            pass

        return now

    def _to_post(self, raw: dict) -> Post:
        """Convert raw Yahoo Finance news to Post model.

        Field mapping:
        - source: "yahoo"
        - source_id: hash of link
        - source_url: news link
        - content: title + summary
        - author_id: news source
        - author_name: news source
        - post_time: published timestamp
        - likes/comments/shares: 0
        """
        link = raw.get("link", "")
        source_id = hashlib.sha256(link.encode()).hexdigest()[:16]

        title = raw.get("title", "")
        summary = raw.get("summary", "")
        content = f"{title}\n\n{summary}".strip() if summary else title

        news_source = raw.get("source", "Yahoo Finance")

        return Post(
            source="yahoo",
            source_id=source_id,
            source_url=link,
            content=content,
            author_id=news_source,
            author_name=news_source,
            post_time=raw.get("published", 0),
            likes=0,
            comments=0,
            shares=0,
        )


# Module-level collector instance
_collector: YahooFinanceCollector | None = None


def _get_collector() -> YahooFinanceCollector:
    """Get or create the module-level collector instance."""
    global _collector
    if _collector is None:
        _collector = YahooFinanceCollector()
    return _collector


def fetch_posts_as_models(
    hours: int,
    symbols: Optional[List[str]] = None,
) -> Tuple[List[Post], int]:
    """Fetch recent news and map them to Post models.

    Args:
        hours: Time window in hours
        symbols: List of stock symbols (None for trending)

    Returns:
        Tuple of (posts, total_count)
    """
    collector = _get_collector()
    return collector.fetch_posts(hours=hours, symbols=symbols)


def sync_stock_price_bars(
    symbol: str,
    *,
    sync_daily: bool = True,
    sync_intraday: bool = True,
    daily_overlap_days: int = 2,
    intraday_overlap_minutes: int = 5,
) -> Dict[str, Any]:
    """Sync adjusted daily and intraday price bars for a single stock symbol.

    Stores data into the `stock_price_bars` table via the `StockPriceBar` model.
    """
    symbol_n = (symbol or "").strip().upper()
    if not symbol_n:
        raise ValueError("symbol is required")

    result: Dict[str, Any] = {"symbol": symbol_n}

    if sync_daily:
        result["daily"] = _sync_yahoo_price_bars(
            symbol_n,
            interval="1d",
            overlap=timedelta(days=daily_overlap_days),
            default_period="max",
            prepost=False,
        )

    if sync_intraday:
        result["intraday"] = _sync_yahoo_intraday_with_fallback(
            symbol_n,
            overlap=timedelta(minutes=intraday_overlap_minutes),
        )

    return result


def _sync_yahoo_intraday_with_fallback(symbol: str, *, overlap: timedelta) -> Dict[str, Any]:
    intervals = ["1m", "2m", "5m", "15m", "30m", "60m"]
    last_error: str | None = None

    for interval in intervals:
        try:
            out = _sync_yahoo_price_bars(
                symbol,
                interval=interval,
                overlap=overlap,
                default_period="7d",
                prepost=True,
            )
            if out.get("raw_rows", 0) > 0:
                return out
            last_error = f"empty data for interval={interval}"
        except Exception as exc:
            last_error = str(exc)
            logger.warning("[yahoo] intraday interval fallback (%s): %s", interval, exc)
            continue

    return {
        "interval": None,
        "raw_rows": 0,
        "fetched_rows": 0,
        "inserted": 0,
        "updated": 0,
        "unchanged": 0,
        "errors": 1,
        "start_ts": None,
        "end_ts": None,
        "error": last_error or "all intraday intervals failed",
    }


def _sync_yahoo_price_bars(
    symbol: str,
    *,
    interval: str,
    overlap: timedelta,
    default_period: str,
    prepost: bool,
) -> Dict[str, Any]:
    try:
        import pandas as pd  # type: ignore
    except Exception as exc:
        raise RuntimeError("pandas is required for price bar sync") from exc

    try:
        import yfinance as yf  # type: ignore
    except Exception as exc:
        raise RuntimeError("yfinance is required for price bar sync") from exc

    symbol_n = (symbol or "").strip().upper()
    interval_n = (interval or "").strip()
    if not symbol_n or not interval_n:
        raise ValueError("symbol and interval are required")

    last_ts = StockPriceBar.get_latest_ts(symbol_n, interval_n)
    overlap_s = int(overlap.total_seconds())
    start_ts = (last_ts - overlap_s) if last_ts is not None else None

    ticker = yf.Ticker(symbol_n)

    df = _fetch_history_df(
        ticker,
        interval=interval_n,
        start_ts=start_ts,
        default_period=default_period,
        prepost=prepost,
    )

    if df is None or df.empty:
        return {
            "interval": interval_n,
            "raw_rows": 0,
            "fetched_rows": 0,
            "inserted": 0,
            "updated": 0,
            "unchanged": 0,
            "errors": 0,
            "start_ts": None,
            "end_ts": None,
        }

    raw_rows = int(len(df))
    df_reset = df.reset_index()
    time_col = df_reset.columns[0]
    ts_utc = pd.to_datetime(df_reset[time_col], utc=True)
    df_reset["ts"] = (ts_utc.astype("int64") // 1_000_000_000).astype("int64")

    col_map = {}
    for c in df_reset.columns:
        lc = str(c).lower()
        if lc in {"open", "high", "low", "close", "volume"}:
            col_map[c] = lc
    df_reset = df_reset.rename(columns=col_map)

    exchange_tz = getattr(df.index, "tz", None)
    df_reset["trade_day"] = _compute_trade_day(ts_utc, exchange_tz)

    if interval_n == "1d":
        df_reset["session"] = "regular"
    else:
        df_reset["session"] = _classify_trading_session(ts_utc, exchange_tz)

    if start_ts is not None:
        df_reset = df_reset[df_reset["ts"] >= int(start_ts)]

    required_cols = ["ts", "trade_day", "open", "high", "low", "close", "volume", "session"]
    for col in required_cols:
        if col not in df_reset.columns:
            raise RuntimeError(f"missing column from yfinance data: {col}")

    df_reset = df_reset.dropna(subset=["ts", "open", "high", "low", "close"])
    if df_reset.empty:
        return {
            "interval": interval_n,
            "raw_rows": raw_rows,
            "fetched_rows": 0,
            "inserted": 0,
            "updated": 0,
            "unchanged": 0,
            "errors": 0,
            "start_ts": None,
            "end_ts": None,
        }

    rows: List[Dict[str, Any]] = []
    for record in df_reset.to_dict(orient="records"):
        rows.append({
            "symbol": symbol_n,
            "interval": interval_n,
            "ts": int(record["ts"]),
            "trade_day": record.get("trade_day"),
            "open": record.get("open"),
            "high": record.get("high"),
            "low": record.get("low"),
            "close": record.get("close"),
            "volume": record.get("volume", 0),
            "session": record.get("session", "unknown"),
        })

    stats = StockPriceBar.save_bars(rows)
    ts_min = int(df_reset["ts"].min())
    ts_max = int(df_reset["ts"].max())

    return {
        "interval": interval_n,
        "raw_rows": raw_rows,
        "fetched_rows": int(len(rows)),
        "inserted": int(stats.get("inserted", 0)),
        "updated": int(stats.get("updated", 0)),
        "unchanged": int(stats.get("unchanged", 0)),
        "errors": int(stats.get("errors", 0)),
        "start_ts": ts_min,
        "end_ts": ts_max,
    }


def _classify_trading_session(ts_utc, exchange_tz):
    import pandas as pd  # type: ignore

    if exchange_tz is None:
        return pd.Series(["unknown"] * len(ts_utc), index=ts_utc.index)

    local = ts_utc.dt.tz_convert(exchange_tz)
    minutes = local.dt.hour * 60 + local.dt.minute
    is_regular = (minutes >= 570) & (minutes < 960)
    return is_regular.map({True: "regular", False: "extended"})


def _compute_trade_day(ts_utc, exchange_tz):
    if exchange_tz is None:
        local = ts_utc
    else:
        local = ts_utc.dt.tz_convert(exchange_tz)
    return local.dt.strftime("%Y%m%d")


def _fetch_history_df(
    ticker: Any,
    *,
    interval: str,
    start_ts: int | None,
    default_period: str,
    prepost: bool,
):
    kwargs: Dict[str, Any] = {
        "interval": interval,
        "auto_adjust": True,
        "prepost": prepost,
        "actions": False,
    }

    if start_ts is not None and start_ts > 0:
        start_dt = datetime.fromtimestamp(start_ts, tz=timezone.utc)
        try:
            df = ticker.history(start=start_dt, **kwargs)
            if df is not None and not df.empty:
                return df
        except Exception as exc:
            logger.warning("[yahoo] history(start=...) failed for %s %s: %s", ticker.ticker, interval, exc)

    return ticker.history(period=default_period, **kwargs)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Yahoo Finance news collector."
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="Time window in hours (default: 24)",
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        help="Stock symbols to fetch (default: trending)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum news items to fetch (default: 10)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    print("=" * 60)
    print("Yahoo Finance Collector")
    print("=" * 60)
    print(f"Hours window: {args.hours}")
    print(f"Symbols: {args.symbols or 'trending'}")
    print(f"Limit: {args.limit}")
    print("-" * 60)

    collector = YahooFinanceCollector()

    now_ts = int(time.time())
    since_ts = now_ts - args.hours * 3600

    if args.symbols:
        for symbol in args.symbols:
            print(f"\nFetching ${symbol}...")
            news = collector.fetch_by_symbol(symbol, limit=args.limit, since_ts=since_ts)
            print(f"  -> {len(news)} news items")

            for i, n in enumerate(news[:5], 1):
                title = n.get("title", "")[:60]
                source = n.get("source", "")
                print(f"  {i}. [{source}] {title}...")
    else:
        print("\nFetching trending news...")
        news = collector.fetch_trending(limit=args.limit, since_ts=since_ts)
        print(f"  -> {len(news)} news items")

        for i, n in enumerate(news[:5], 1):
            title = n.get("title", "")[:60]
            source = n.get("source", "")
            print(f"  {i}. [{source}] {title}...")

    print("\n" + "=" * 60)
