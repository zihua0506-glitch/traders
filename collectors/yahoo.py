"""Yahoo Finance news collector module.

Fetches financial news from Yahoo Finance RSS feeds and web pages.
"""

from __future__ import annotations

import hashlib
import logging
import time
import urllib3
from typing import List, Tuple, Optional
from datetime import datetime

from bs4 import BeautifulSoup

from models import Post
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
