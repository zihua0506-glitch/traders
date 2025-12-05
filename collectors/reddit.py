"""Reddit collector module.

This module defines constants and utilities to collect posts from
predefined subreddits. Uses direct .json endpoint requests (no API key required).

Based on YARS (Yet Another Reddit Scraper) approach.
"""

from __future__ import annotations

import json
import logging
import random
import time
from typing import List, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from models import Post


# Logger
logger = logging.getLogger(__name__)

# Target subreddit communities to collect from.
SUBREDDITS = [
    "wallstreetbets",
    "stocks",
    "investing",
]

# Random user agents to avoid detection
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

# Configuration
REQUEST_TIMEOUT = 15
MAX_POSTS_PER_REQUEST = 100
RATE_LIMIT_DELAY = (1.0, 2.0)  # Random delay range in seconds


class RedditScraper:
    """Reddit scraper using public .json endpoints (no API key required).

    This is a YARS-style implementation that scrapes Reddit without
    requiring official API credentials.
    """

    def __init__(self, timeout: int = REQUEST_TIMEOUT):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "application/json",
        })

        # Configure retries for resilience
        retries = Retry(
            total=3,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retries))

    def fetch_subreddit_posts(
        self,
        subreddit: str,
        limit: int = 100,
        category: str = "new",
        time_filter: str = "all",
        since_ts: int = 0,
    ) -> List[dict]:
        """Fetch posts from a subreddit.

        Args:
            subreddit: Subreddit name (without r/)
            limit: Maximum number of posts to fetch
            category: Sort category - "hot", "new", "top", "rising"
            time_filter: Time filter for "top" - "hour", "day", "week", "month", "year", "all"
            since_ts: Unix timestamp; only return posts created after this time

        Returns:
            List of post dictionaries with raw Reddit data
        """
        url = f"https://www.reddit.com/r/{subreddit}/{category}.json"
        params = {
            "limit": min(MAX_POSTS_PER_REQUEST, limit),
            "raw_json": 1,
            "t": time_filter,
        }

        all_posts = []
        after = None

        while len(all_posts) < limit:
            if after:
                params["after"] = after

            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
                response.raise_for_status()
            except requests.exceptions.RequestException as e:
                logger.error("Request to r/%s failed: %s", subreddit, e)
                break

            try:
                data = response.json()
            except json.JSONDecodeError as e:
                logger.error("JSON decode error for r/%s: %s", subreddit, e)
                break

            posts = data.get("data", {}).get("children", [])
            if not posts:
                break

            for post in posts:
                post_data = post.get("data", {})
                created_utc = int(post_data.get("created_utc", 0))

                # Time window filter: skip posts older than since_ts
                if since_ts and created_utc < since_ts:
                    # Posts are sorted newest first, so we can stop here
                    return all_posts[:limit]

                post_info = {
                    "id": post_data.get("id", ""),
                    "name": post_data.get("name", ""),
                    "title": post_data.get("title", ""),
                    "author": post_data.get("author", ""),
                    "selftext": post_data.get("selftext", ""),
                    "permalink": post_data.get("permalink", ""),
                    "url": post_data.get("url", ""),
                    "score": post_data.get("score", 0),
                    "num_comments": post_data.get("num_comments", 0),
                    "created_utc": created_utc,
                    "subreddit": post_data.get("subreddit", ""),
                }
                all_posts.append(post_info)

                if len(all_posts) >= limit:
                    break

            after = data.get("data", {}).get("after")
            if not after:
                break

            # Rate limiting - be nice to Reddit
            time.sleep(random.uniform(*RATE_LIMIT_DELAY))

        return all_posts[:limit]


# Module-level scraper instance
_scraper: RedditScraper | None = None


def _get_scraper() -> RedditScraper:
    """Get or create the module-level scraper instance."""
    global _scraper
    if _scraper is None:
        _scraper = RedditScraper()
    return _scraper


def fetch_posts(hours: int) -> List[dict]:
    """Fetch posts from configured subreddits within the last N hours.

    Args:
        hours: Positive integer number of hours to look back from now.

    Returns:
        A list of raw post dictionaries from Reddit.

    Raises:
        ValueError: If `hours` is not a positive integer.
    """
    if not isinstance(hours, int) or hours <= 0:
        raise ValueError("hours must be a positive integer")

    now_ts = int(time.time())
    since_ts = now_ts - hours * 3600

    scraper = _get_scraper()
    collected: List[dict] = []

    for name in SUBREDDITS:
        try:
            logger.info("Fetching posts from r/%s (since %d hours ago)", name, hours)
            posts = scraper.fetch_subreddit_posts(
                subreddit=name,
                limit=1000,
                category="new",
                since_ts=since_ts,
            )
            collected.extend(posts)
            logger.info("Collected %d posts from r/%s", len(posts), name)
        except Exception as exc:
            logger.error(
                "Error collecting from subreddit '%s': %s", name, exc, exc_info=True
            )
            continue

    return collected


def _raw_post_to_model(raw: dict) -> Post:
    """Map a raw Reddit post dict to a normalized Post dataclass.

    Field mapping:
    - content: title + selftext
    - source: constant 'reddit'
    - source_id: post id
    - source_url: permalink
    - post_time: created_utc
    - likes: score
    - comments: num_comments
    - shares: 0 (no Reddit concept)
    - author_id: empty (not available without API)
    - author_name: author username
    """
    title = raw.get("title", "") or ""
    body = raw.get("selftext", "") or ""
    content = f"{title}\n\n{body}".strip()

    permalink = raw.get("permalink", "")
    if permalink and not permalink.startswith("http"):
        source_url = f"https://www.reddit.com{permalink}"
    else:
        source_url = permalink or raw.get("url", "")

    return Post(
        source="reddit",
        source_id=str(raw.get("id", "")),
        source_url=source_url,
        content=content,
        author_id="",  # Not available without API auth
        author_name=str(raw.get("author", "[deleted]")),
        post_time=int(raw.get("created_utc", 0)),
        likes=int(raw.get("score", 0)),
        comments=int(raw.get("num_comments", 0)),
        shares=0,
    )


def fetch_posts_as_models(hours: int) -> Tuple[List[Post], int]:
    """Fetch recent posts and map them to Post models.

    Returns a tuple of (`posts`, `total_count`) to make the collector's
    statistics explicit for downstream aggregation.
    """
    raw_posts = fetch_posts(hours)
    posts = [_raw_post_to_model(p) for p in raw_posts]
    return posts, len(posts)


if __name__ == "__main__":
    import argparse
    import sys
    from collections import Counter

    parser = argparse.ArgumentParser(
        description="Reddit collector: fetch posts from subreddits (no API key required)."
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="Time window in hours (default: 24)",
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

    print(f"Target subreddits: {', '.join(SUBREDDITS)}")
    print(f"Hours window: {args.hours}")
    print("-" * 60)

    try:
        posts, total = fetch_posts_as_models(args.hours)
    except Exception as exc:
        logger.error("Collector error: %s", exc, exc_info=True)
        posts, total = [], 0

    # Per-subreddit breakdown
    counts: Counter = Counter()
    for p in posts:
        # Extract subreddit from source_url
        parts = p.source_url.split("/r/")
        if len(parts) > 1:
            sr = parts[1].split("/")[0]
            counts[sr] += 1

    print(f"\nCollected posts: {total}")
    for name in SUBREDDITS:
        print(f"  - {name}: {counts.get(name, 0)}")

    # Show sample post
    if posts:
        print("\n" + "=" * 60)
        print("Sample post:")
        print("=" * 60)
        sample = posts[0]
        print(f"Title: {sample.content[:100]}...")
        print(f"Author: {sample.author_name}")
        print(f"Score: {sample.likes} | Comments: {sample.comments}")
        print(f"URL: {sample.source_url}")
        print(f"Hash: {sample.content_hash[:16]}...")
