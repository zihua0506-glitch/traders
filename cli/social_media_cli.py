"""CLI: fetch social media posts from X (Twitter) and Reddit."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import importlib.util

# ---------------------------------------------------------------------------
# X (Twitter) fetching
# ---------------------------------------------------------------------------

X_USER_LIST_PATH = os.path.join(PROJECT_ROOT, "x_user_id.json")
_x_api = None


def _load_x_api():
    global _x_api
    if _x_api is None:
        api_path = os.path.join(PROJECT_ROOT, "collectors", "x-rapid-api.py")
        spec = importlib.util.spec_from_file_location("x_rapid_api", api_path)
        _x_api = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_x_api)
    return _x_api


def _format_tweet(t: dict) -> str:
    screen_name = t["author"]["screen_name"] or "unknown"
    raw_time = t["created_at"] or ""
    try:
        utc_dt = datetime.strptime(raw_time, "%a %b %d %H:%M:%S %z %Y")
        created_at = utc_dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        created_at = raw_time
    text = (t["full_text"] or "").replace("\n", " ").strip()
    m = t["metrics"]

    line = f"[@{screen_name} {created_at}] {text}"
    line += f" | views={m['views']} likes={m['favorite_count']} rt={m['retweet_count']}"

    if t["is_retweet"] and t["retweet_of"]:
        rt = t["retweet_of"]
        rt_text = (rt["full_text"] or "").replace("\n", " ").strip()
        line += f" [RETWEET of @{rt['author']['screen_name']}]: {rt_text}"

    if t["is_quote"] and t["quote_of"]:
        qt = t["quote_of"]
        qt_text = (qt["full_text"] or "").replace("\n", " ").strip()
        line += f" [QUOTE of @{qt['author']['screen_name']}]: {qt_text}"

    return line


def fetch_x(minutes: int) -> list[str]:
    if not os.path.exists(X_USER_LIST_PATH):
        print("[X] x_user_id.json not found, skipping.", file=sys.stderr)
        return []

    api = _load_x_api()
    with open(X_USER_LIST_PATH, "r", encoding="utf-8") as f:
        users = json.load(f)

    recent_hours = minutes / 60.0
    lines = []
    for user in users:
        user_id = user["user_id"]
        label = user.get("label", user_id)
        print(f"[X] Fetching tweets for {label} ({user_id})...", file=sys.stderr)

        try:
            tweets = api.fetch_tweets(
                user_id, count=20, recent_hours=recent_hours, max_count=20,
            )
        except Exception as e:
            print(f"[X] Error fetching {label}: {e}", file=sys.stderr)
            continue

        for t in tweets:
            lines.append(_format_tweet(t))

    print(f"[X] Collected {len(lines)} tweets.", file=sys.stderr)
    return lines


# ---------------------------------------------------------------------------
# Reddit fetching
# ---------------------------------------------------------------------------

SUBREDDITS_FILE = os.path.join(PROJECT_ROOT, "subreddits.json")


def _load_subreddits() -> list[str]:
    with open(SUBREDDITS_FILE, "r", encoding="utf-8") as f:
        entries = json.load(f)
    return [entry["subreddit"] for entry in entries]


def _format_reddit_post(post: dict) -> str:
    subreddit = post.get("subreddit", "")
    author = post.get("author", "[deleted]")
    title = (post.get("title", "") or "").replace("\n", " ").strip()
    selftext = (post.get("selftext", "") or "").replace("\n", " ").strip()
    score = post.get("score", 0)
    num_comments = post.get("num_comments", 0)
    created_utc = post.get("created_utc", 0)
    dt = datetime.fromtimestamp(created_utc).strftime("%Y-%m-%d %H:%M:%S")
    permalink = post.get("permalink", "")

    line = f"[r/{subreddit} {dt} u/{author}] {title}"
    if selftext:
        line += f" | {selftext[:200]}"
    line += f" | score={score} comments={num_comments}"
    if permalink:
        line += f" | https://www.reddit.com{permalink}"
    return line


def fetch_reddit(minutes: int) -> list[str]:
    if not os.path.exists(SUBREDDITS_FILE):
        print("[Reddit] subreddits.json not found, skipping.", file=sys.stderr)
        return []

    from collectors.reddit import RedditCollector

    subreddits = _load_subreddits()
    collector = RedditCollector()
    since_ts = int(time.time()) - minutes * 60

    lines = []
    for sub in subreddits:
        print(f"[Reddit] Fetching posts from r/{sub}...", file=sys.stderr)
        try:
            posts = collector.fetch_subreddit_posts(
                subreddit=sub, limit=100, category="new", since_ts=since_ts,
            )
            for p in posts:
                lines.append(_format_reddit_post(p))
            print(f"[Reddit] Collected {len(posts)} posts from r/{sub}.", file=sys.stderr)
        except Exception as e:
            print(f"[Reddit] Error fetching r/{sub}: {e}", file=sys.stderr)
            continue

    print(f"[Reddit] Collected {len(lines)} posts total.", file=sys.stderr)
    return lines


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Fetch social media posts from X and Reddit.",
    )
    parser.add_argument(
        "--minutes", type=int, default=1440,
        help="Time filter: only show posts from the last N minutes (default: 1440 = 24h)",
    )
    args = parser.parse_args()

    x_lines = fetch_x(args.minutes)
    reddit_lines = fetch_reddit(args.minutes)

    if x_lines:
        print("\n=== X (Twitter) ===")
        for line in x_lines:
            print(line)

    if reddit_lines:
        print("\n=== Reddit ===")
        for line in reddit_lines:
            print(line)

    if not x_lines and not reddit_lines:
        print("No posts found.")


if __name__ == "__main__":
    main()
