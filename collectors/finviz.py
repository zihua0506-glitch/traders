"""Finviz news collector module.

Fetches aggregated financial news from Finviz.com.
Finviz aggregates news from multiple sources (Benzinga, Reuters, etc.)
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
import urllib3
from datetime import datetime, timedelta
from typing import List, Tuple, Optional

from bs4 import BeautifulSoup

from models import Post
from .base import BaseCollector


# Suppress SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

# Finviz URLs
QUOTE_URL = "https://finviz.com/quote.ashx?t={symbol}"
NEWS_URL = "https://finviz.com/news.ashx"


class FinvizCollector(BaseCollector):
    """Finviz news collector.

    Scrapes news from Finviz stock pages and news page.
    Finviz aggregates news from multiple financial sources.
    """

    source_name = "finviz"

    def __init__(self, timeout: int = 15, delay: float = 1.0):
        # Finviz needs longer delay to avoid rate limiting
        super().__init__(timeout=timeout, delay=delay)
        # Finviz requires browser-like headers
        self.session.headers.update({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
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
        url = QUOTE_URL.format(symbol=symbol.upper())

        try:
            response = self._get(url, verify=False)
            response.raise_for_status()
        except Exception as e:
            logger.error("[finviz] Failed to fetch %s: %s", symbol, e)
            return []

        return self._parse_news_table(response.text, symbol, limit, since_ts)

    def fetch_trending(
        self,
        limit: int = 50,
        since_ts: int = 0,
    ) -> List[dict]:
        """Fetch latest news from Finviz news page.

        Args:
            limit: Maximum number of news items
            since_ts: Only return items after this timestamp

        Returns:
            List of raw news dictionaries
        """
        try:
            response = self._get(NEWS_URL, verify=False)
            response.raise_for_status()
        except Exception as e:
            logger.error("[finviz] Failed to fetch news page: %s", e)
            return []

        return self._parse_news_page(response.text, limit, since_ts)

    def _parse_news_table(
        self,
        html: str,
        symbol: str,
        limit: int,
        since_ts: int,
    ) -> List[dict]:
        """Parse news table from Finviz stock page.

        The news table has format:
        <table id="news-table">
          <tr>
            <td width="130">Dec-05-24 10:30AM</td>
            <td><a href="...">News Title</a><span>Source</span></td>
          </tr>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")

        # Find news table
        news_table = soup.find("table", {"id": "news-table"})
        if not news_table:
            # Try alternative class name
            news_table = soup.find("table", class_="fullview-news-outer")

        if not news_table:
            logger.warning("[finviz] News table not found for symbol")
            return []

        news = []
        current_date = None

        for row in news_table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue

            # First cell: date/time
            date_cell = cells[0].get_text().strip()

            # Parse date - could be full date or just time
            parsed_time = self._parse_finviz_time(date_cell, current_date)
            if parsed_time:
                # If we got a full date, remember it
                if re.match(r"[A-Za-z]{3}-\d{2}-\d{2}", date_cell):
                    current_date = date_cell.split()[0]

            # Time filter
            if since_ts and parsed_time and parsed_time < since_ts:
                continue

            # Second cell: link and source
            link_cell = cells[1]
            link_tag = link_cell.find("a")

            if not link_tag:
                continue

            title = link_tag.get_text().strip()
            href = link_tag.get("href", "")

            # Get source (usually in a span after the link)
            source = "Finviz"
            source_span = link_cell.find("span")
            if source_span:
                source = source_span.get_text().strip()

            news.append({
                "title": title,
                "link": href,
                "source": source,
                "published": parsed_time or int(time.time()),
                "_symbol": symbol.upper(),
            })

            if len(news) >= limit:
                break

        return news

    def _parse_news_page(
        self,
        html: str,
        limit: int,
        since_ts: int,
    ) -> List[dict]:
        """Parse Finviz main news page."""
        soup = BeautifulSoup(html, "html.parser")

        news = []

        # Find news tables (there are usually multiple sections)
        tables = soup.find_all("table", class_="news_table")

        if not tables:
            # Try alternative structure
            tables = soup.find_all("table", {"id": lambda x: x and "news" in x.lower()})

        for table in tables:
            for row in table.find_all("tr"):
                cells = row.find_all("td")

                # Find the link
                link_tag = row.find("a", class_="nn-tab-link") or row.find("a")
                if not link_tag:
                    continue

                title = link_tag.get_text().strip()
                href = link_tag.get("href", "")

                if not title or len(title) < 10:
                    continue

                # Get source
                source = "Finviz"
                source_span = row.find("span", class_="nn-tab-link-source")
                if source_span:
                    source = source_span.get_text().strip()

                # Get time
                time_cell = row.find("td", class_="nn-tab-link-time")
                parsed_time = int(time.time())
                if time_cell:
                    time_text = time_cell.get_text().strip()
                    parsed_time = self._parse_finviz_time(time_text, None) or parsed_time

                if since_ts and parsed_time < since_ts:
                    continue

                news.append({
                    "title": title,
                    "link": href,
                    "source": source,
                    "published": parsed_time,
                    "_symbol": "",
                })

                if len(news) >= limit:
                    return news

        return news

    def _parse_finviz_time(self, time_str: str, base_date: str = None) -> int:
        """Parse Finviz time format to Unix timestamp.

        Formats:
        - "Dec-05-24 10:30AM" (full date with time)
        - "10:30AM" (time only, use base_date or today)
        - "Today 10:30AM"
        - "Yesterday 10:30AM"
        """
        if not time_str:
            return 0

        time_str = time_str.strip()
        now = datetime.now()

        try:
            # Full date format: Dec-05-24 10:30AM
            if re.match(r"[A-Za-z]{3}-\d{2}-\d{2}", time_str):
                parts = time_str.split()
                date_part = parts[0]
                time_part = parts[1] if len(parts) > 1 else "12:00PM"

                dt = datetime.strptime(f"{date_part} {time_part}", "%b-%d-%y %I:%M%p")
                return int(dt.timestamp())

            # Time only format: 10:30AM
            if re.match(r"\d{1,2}:\d{2}[AP]M", time_str, re.IGNORECASE):
                if base_date:
                    dt = datetime.strptime(f"{base_date} {time_str}", "%b-%d-%y %I:%M%p")
                else:
                    # Use today's date
                    today = now.strftime("%b-%d-%y")
                    dt = datetime.strptime(f"{today} {time_str}", "%b-%d-%y %I:%M%p")
                return int(dt.timestamp())

            # "Today" prefix
            if time_str.lower().startswith("today"):
                time_part = time_str.split(maxsplit=1)[1] if " " in time_str else "12:00PM"
                today = now.strftime("%b-%d-%y")
                dt = datetime.strptime(f"{today} {time_part}", "%b-%d-%y %I:%M%p")
                return int(dt.timestamp())

            # "Yesterday" prefix
            if time_str.lower().startswith("yesterday"):
                time_part = time_str.split(maxsplit=1)[1] if " " in time_str else "12:00PM"
                yesterday = (now - timedelta(days=1)).strftime("%b-%d-%y")
                dt = datetime.strptime(f"{yesterday} {time_part}", "%b-%d-%y %I:%M%p")
                return int(dt.timestamp())

        except Exception as e:
            logger.debug("[finviz] Failed to parse time '%s': %s", time_str, e)

        return 0

    def _to_post(self, raw: dict) -> Post:
        """Convert raw Finviz news to Post model.

        Field mapping:
        - source: "finviz"
        - source_id: hash of link
        - source_url: news link
        - content: title
        - author_id: news source (Benzinga, Reuters, etc.)
        - author_name: news source
        - post_time: published timestamp
        - likes/comments/shares: 0
        """
        link = raw.get("link", "")
        source_id = hashlib.sha256(link.encode()).hexdigest()[:16]

        title = raw.get("title", "")
        news_source = raw.get("source", "Finviz")

        return Post(
            source="finviz",
            source_id=source_id,
            source_url=link,
            content=title,
            author_id=news_source,
            author_name=news_source,
            post_time=raw.get("published", 0),
            likes=0,
            comments=0,
            shares=0,
        )


# Module-level collector instance
_collector: FinvizCollector | None = None


def _get_collector() -> FinvizCollector:
    """Get or create the module-level collector instance."""
    global _collector
    if _collector is None:
        _collector = FinvizCollector()
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
        description="Finviz news collector."
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
    print("Finviz Collector")
    print("=" * 60)
    print(f"Hours window: {args.hours}")
    print(f"Symbols: {args.symbols or 'trending'}")
    print(f"Limit: {args.limit}")
    print("-" * 60)

    collector = FinvizCollector()

    now_ts = int(time.time())
    since_ts = now_ts - args.hours * 3600

    if args.symbols:
        for symbol in args.symbols:
            print(f"\nFetching ${symbol}...")
            news = collector.fetch_by_symbol(symbol, limit=args.limit, since_ts=since_ts)
            print(f"  -> {len(news)} news items")

            for i, n in enumerate(news[:5], 1):
                title = n.get("title", "")[:55]
                source = n.get("source", "")
                print(f"  {i}. [{source}] {title}...")
    else:
        print("\nFetching trending news...")
        news = collector.fetch_trending(limit=args.limit, since_ts=since_ts)
        print(f"  -> {len(news)} news items")

        for i, n in enumerate(news[:5], 1):
            title = n.get("title", "")[:55]
            source = n.get("source", "")
            print(f"  {i}. [{source}] {title}...")

    print("\n" + "=" * 60)
