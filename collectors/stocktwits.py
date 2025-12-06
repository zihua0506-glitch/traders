"""StockTwits collector module.

Fetches posts from StockTwits API. No API key required for basic access.
Users can tag posts with sentiment (Bullish/Bearish).

NOTE: StockTwits has Cloudflare protection that blocks Python requests.
This collector may return empty results. Consider using browser automation
(Playwright/Selenium) for reliable access, or use the unofficial RSS feeds.
"""

from __future__ import annotations

import logging
import time
from typing import List, Tuple, Optional
from datetime import datetime

from models import Post
from .base import BaseCollector


logger = logging.getLogger(__name__)

# StockTwits API endpoints
API_BASE = "https://api.stocktwits.com/api/2"
SYMBOL_STREAM_URL = f"{API_BASE}/streams/symbol/{{symbol}}.json"
TRENDING_URL = f"{API_BASE}/streams/trending.json"
HOME_URL = f"{API_BASE}/streams/home.json"


class StockTwitsCollector(BaseCollector):
    """StockTwits collector using public API.

    StockTwits provides a free API for accessing public streams.
    Posts may include user-tagged sentiment (Bullish/Bearish).
    """

    source_name = "stocktwits"

    def __init__(self, timeout: int = 15, delay: float = 0.5):
        super().__init__(timeout=timeout, delay=delay)
        # StockTwits requires specific headers
        self.session.headers.update({
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://stocktwits.com/",
            "Origin": "https://stocktwits.com",
        })

    def fetch_by_symbol(
        self,
        symbol: str,
        limit: int = 50,
        since_ts: int = 0,
    ) -> List[dict]:
        """Fetch posts for a specific stock symbol.

        Args:
            symbol: Stock ticker symbol (e.g., "AAPL")
            limit: Maximum number of posts to fetch
            since_ts: Only return posts after this timestamp

        Returns:
            List of raw message dictionaries
        """
        url = SYMBOL_STREAM_URL.format(symbol=symbol.upper())
        params = {"limit": min(limit, 30)}  # API max is 30 per request

        all_messages = []
        max_id = None

        while len(all_messages) < limit:
            if max_id:
                params["max"] = max_id

            try:
                response = self._get(url, params=params)
                response.raise_for_status()
                data = response.json()
            except Exception as e:
                logger.error("[stocktwits] Failed to fetch %s: %s", symbol, e)
                break

            # Check for API errors
            if data.get("response", {}).get("status") != 200:
                error = data.get("errors", [{}])[0].get("message", "Unknown error")
                logger.error("[stocktwits] API error for %s: %s", symbol, error)
                break

            messages = data.get("messages", [])
            if not messages:
                break

            for msg in messages:
                created_at = self._parse_time(msg.get("created_at", ""))

                # Time window filter
                if since_ts and created_at < since_ts:
                    return all_messages[:limit]

                msg["_parsed_time"] = created_at
                msg["_symbol"] = symbol.upper()
                all_messages.append(msg)

                if len(all_messages) >= limit:
                    break

            # Get cursor for pagination
            cursor = data.get("cursor", {})
            max_id = cursor.get("max")
            if not max_id:
                break

            self._rate_limit()

        return all_messages[:limit]

    def fetch_trending(
        self,
        limit: int = 50,
        since_ts: int = 0,
    ) -> List[dict]:
        """Fetch trending posts from StockTwits.

        Args:
            limit: Maximum number of posts to fetch
            since_ts: Only return posts after this timestamp

        Returns:
            List of raw message dictionaries
        """
        url = TRENDING_URL
        params = {"limit": min(limit, 30)}

        all_messages = []
        max_id = None

        while len(all_messages) < limit:
            if max_id:
                params["max"] = max_id

            try:
                response = self._get(url, params=params)
                response.raise_for_status()
                data = response.json()
            except Exception as e:
                logger.error("[stocktwits] Failed to fetch trending: %s", e)
                break

            if data.get("response", {}).get("status") != 200:
                error = data.get("errors", [{}])[0].get("message", "Unknown error")
                logger.error("[stocktwits] API error: %s", error)
                break

            messages = data.get("messages", [])
            if not messages:
                break

            for msg in messages:
                created_at = self._parse_time(msg.get("created_at", ""))

                if since_ts and created_at < since_ts:
                    return all_messages[:limit]

                msg["_parsed_time"] = created_at
                all_messages.append(msg)

                if len(all_messages) >= limit:
                    break

            cursor = data.get("cursor", {})
            max_id = cursor.get("max")
            if not max_id:
                break

            self._rate_limit()

        return all_messages[:limit]

    def _parse_time(self, time_str: str) -> int:
        """Parse StockTwits time format to Unix timestamp.

        Format: "2024-01-15T10:30:00Z"
        """
        if not time_str:
            return 0

        try:
            # Handle ISO format with Z suffix
            if time_str.endswith("Z"):
                time_str = time_str[:-1] + "+00:00"
            dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
            return int(dt.timestamp())
        except Exception:
            return 0

    def _extract_sentiment(self, msg: dict) -> str:
        """Extract user-tagged sentiment from message.

        Returns: "bullish", "bearish", or "" (no sentiment tagged)
        """
        entities = msg.get("entities", {})
        sentiment = entities.get("sentiment", {})
        basic = sentiment.get("basic")

        if basic:
            return basic.lower()  # "Bullish" -> "bullish"
        return ""

    def _extract_tickers(self, msg: dict) -> List[str]:
        """Extract ticker symbols mentioned in the message."""
        entities = msg.get("entities", {})
        symbols = entities.get("symbols", [])
        return [s.get("symbol", "") for s in symbols if s.get("symbol")]

    def _to_post(self, raw: dict) -> Post:
        """Convert raw StockTwits message to Post model.

        Field mapping:
        - source: "stocktwits"
        - source_id: message id
        - source_url: constructed from id
        - content: message body
        - author_id: user id
        - author_name: username
        - post_time: created_at parsed
        - likes: likes.total
        - comments: 0 (not available in API)
        - shares: 0
        """
        msg_id = str(raw.get("id", ""))
        user = raw.get("user", {})

        # Build source URL
        username = user.get("username", "")
        source_url = f"https://stocktwits.com/{username}/message/{msg_id}"

        # Get body content
        body = raw.get("body", "")

        # Extract sentiment and tickers for metadata
        sentiment = self._extract_sentiment(raw)
        tickers = self._extract_tickers(raw)

        # Add sentiment/tickers to content for LLM context
        content = body
        if sentiment:
            content = f"[{sentiment.upper()}] {content}"
        if tickers and raw.get("_symbol"):
            # Already have symbol context
            pass

        return Post(
            source="stocktwits",
            source_id=msg_id,
            source_url=source_url,
            content=content,
            author_id=str(user.get("id", "")),
            author_name=user.get("username", ""),
            post_time=raw.get("_parsed_time", 0),
            likes=raw.get("likes", {}).get("total", 0) if isinstance(raw.get("likes"), dict) else 0,
            comments=0,  # Not available in API response
            shares=0,
        )


# Module-level collector instance
_collector: StockTwitsCollector | None = None


def _get_collector() -> StockTwitsCollector:
    """Get or create the module-level collector instance."""
    global _collector
    if _collector is None:
        _collector = StockTwitsCollector()
    return _collector


def fetch_posts_as_models(
    hours: int,
    symbols: Optional[List[str]] = None,
) -> Tuple[List[Post], int]:
    """Fetch recent posts and map them to Post models.

    Args:
        hours: Time window in hours
        symbols: List of stock symbols to fetch (None for trending)

    Returns:
        Tuple of (posts, total_count)
    """
    collector = _get_collector()
    return collector.fetch_posts(hours=hours, symbols=symbols)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="StockTwits collector: fetch posts from StockTwits API."
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
        default=20,
        help="Maximum posts to fetch (default: 20)",
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
    print("StockTwits Collector")
    print("=" * 60)
    print(f"Hours window: {args.hours}")
    print(f"Symbols: {args.symbols or 'trending'}")
    print(f"Limit: {args.limit}")
    print("-" * 60)

    collector = StockTwitsCollector()

    now_ts = int(time.time())
    since_ts = now_ts - args.hours * 3600

    if args.symbols:
        for symbol in args.symbols:
            print(f"\nFetching ${symbol}...")
            posts = collector.fetch_by_symbol(symbol, limit=args.limit, since_ts=since_ts)
            print(f"  -> {len(posts)} posts")

            for i, p in enumerate(posts[:3], 1):
                sentiment = collector._extract_sentiment(p)
                body = p.get("body", "")[:60]
                tag = f"[{sentiment.upper()}]" if sentiment else ""
                print(f"  {i}. {tag} {body}...")
    else:
        print("\nFetching trending...")
        posts = collector.fetch_trending(limit=args.limit, since_ts=since_ts)
        print(f"  -> {len(posts)} posts")

        for i, p in enumerate(posts[:5], 1):
            sentiment = collector._extract_sentiment(p)
            tickers = collector._extract_tickers(p)
            body = p.get("body", "")[:50]
            tag = f"[{sentiment.upper()}]" if sentiment else ""
            syms = " ".join(f"${t}" for t in tickers[:3])
            print(f"  {i}. {tag} {syms} {body}...")

    print("\n" + "=" * 60)
