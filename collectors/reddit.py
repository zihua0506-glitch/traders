"""Reddit collector module.

This module defines constants and utilities to collect posts from
predefined subreddits. Implements time-window filtering via
``fetch_posts(hours: int)`` using the PRAW library.
"""

from __future__ import annotations

import os
import time
from typing import List

try:
    import praw  # type: ignore
except Exception:  # pragma: no cover - import-time environment varies
    praw = None  # type: ignore


# Target subreddit communities to collect from.
SUBREDDITS = [
    "wallstreetbets",
    "stocks",
    "investing",
]


def _make_reddit_client() -> "praw.Reddit":
    """Create and return a authenticated PRAW Reddit client.

    Reads credentials from environment variables:
    - `REDDIT_CLIENT_ID`
    - `REDDIT_CLIENT_SECRET`
    - `REDDIT_USER_AGENT` (optional)

    Raises a RuntimeError when PRAW is not installed or credentials are missing.
    """

    if praw is None:
        raise RuntimeError(
            "praw is not installed. Please install 'praw' to use the Reddit collector."
        )

    client_id = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    user_agent = os.getenv(
        "REDDIT_USER_AGENT", "sentiment-collector/0.1 (+https://example.invalid)"
    )

    if not client_id or not client_secret:
        raise RuntimeError(
            "Missing Reddit API credentials. Set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET."
        )

    return praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=user_agent,
    )


def fetch_posts(hours: int) -> List["praw.models.Submission"]:
    """Fetch submissions from configured subreddits within the last N hours.

    Args:
        hours: Positive integer number of hours to look back from now.

    Returns:
        A list of PRAW `Submission` objects whose `created_utc` is within the
        specified time window.

    Raises:
        ValueError: If `hours` is not a positive integer.
        RuntimeError: If PRAW is not available or credentials are missing.
    """

    if not isinstance(hours, int) or hours <= 0:
        raise ValueError("hours must be a positive integer")

    now_ts = int(time.time())
    since_ts = now_ts - hours * 3600

    reddit = _make_reddit_client()

    collected: List["praw.models.Submission"] = []
    for name in SUBREDDITS:
        subreddit = reddit.subreddit(name)
        # Iterate newest-to-oldest; break early once outside the window.
        for submission in subreddit.new(limit=1000):
            created = getattr(submission, "created_utc", None)
            if created is None:
                continue
            if int(created) >= since_ts:
                collected.append(submission)
            else:
                # Listing is newest-first; once older than window, move to next subreddit
                break

    return collected


if __name__ == "__main__":
    import argparse
    import sys
    from collections import Counter

    parser = argparse.ArgumentParser(
        description="Reddit collector quick check: list target subreddits and count posts within a time window."
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="Time window in hours (default: 24)",
    )
    args = parser.parse_args()

    print(f"Target subreddits: {', '.join(SUBREDDITS)}")
    print(f"Hours window: {args.hours}")

    try:
        submissions = fetch_posts(args.hours)
    except Exception as exc:  # keep CLI resilient for quick validation
        print(f"Error collecting posts: {exc}", file=sys.stderr)
        sys.exit(1)

    total = len(submissions)
    # Per-subreddit breakdown for easier validation
    counts = Counter()
    for s in submissions:
        sr_name = getattr(getattr(s, "subreddit", None), "display_name", None)
        if not sr_name:
            sr_name = str(getattr(s, "subreddit", "unknown"))
        counts[sr_name] += 1

    print(f"Collected posts: {total}")
    for name in SUBREDDITS:
        print(f"  - {name}: {counts.get(name, 0)}")
