"""Reddit collector module.

This module defines constants and utilities to collect posts from
predefined subreddits. Implements time-window filtering via
``fetch_posts(hours: int)`` using the PRAW library.
"""

from __future__ import annotations

import os
import time
from typing import List

# Models
from models import Post

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


def _submission_to_post(submission: "praw.models.Submission") -> Post:
    """Map a PRAW Submission to a normalized Post dataclass.

    Field mapping rules (per spec):
    - content: title + body (selftext)
    - source: constant 'reddit'
    - source_id: submission.id
    - source_url: prefer permalink; fallback to submission.url
    - post_time: submission.created_utc
    - likes: submission.score
    - comments: submission.num_comments
    - shares: 0 (no Reddit concept)
    - author_id/author_name: from submission.author (handle None)
    """

    title = getattr(submission, "title", "") or ""
    body = getattr(submission, "selftext", "") or ""
    content = f"{title}\n\n{body}".strip()

    # Prefer a canonical reddit permalink if available
    permalink = getattr(submission, "permalink", None)
    if permalink:
        if not str(permalink).startswith("http"):
            source_url = f"https://www.reddit.com{permalink}"
        else:
            source_url = str(permalink)
    else:
        source_url = str(getattr(submission, "url", ""))

    author = getattr(submission, "author", None)
    author_id = getattr(author, "id", "") if author is not None else ""
    author_name = getattr(author, "name", "") if author is not None else "[deleted]"

    return Post(
        source="reddit",
        source_id=str(getattr(submission, "id", "")),
        source_url=source_url,
        content=content,
        author_id=str(author_id) if author_id is not None else "",
        author_name=str(author_name),
        post_time=int(getattr(submission, "created_utc", 0) or 0),
        likes=int(getattr(submission, "score", 0) or 0),
        comments=int(getattr(submission, "num_comments", 0) or 0),
        shares=0,
    )


def fetch_posts_as_models(hours: int) -> List[Post]:
    """Fetch recent submissions and map them to Post models.

    Keeps `fetch_posts` behavior intact for callers that need raw PRAW objects,
    while providing a normalized `Post` list for downstream processing.
    """
    raw = fetch_posts(hours)
    return [_submission_to_post(s) for s in raw]


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
