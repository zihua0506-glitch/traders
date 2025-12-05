"""Test cases for Reddit collector.

Run with: python -m pytest tests/test_collector.py -v
Or simply: python tests/test_collector.py
"""

import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from collectors.reddit import (
    RedditScraper,
    fetch_posts,
    fetch_posts_as_models,
    SUBREDDITS,
)
from models import Post


def test_scraper_fetch_wallstreetbets():
    """Test fetching posts from r/wallstreetbets."""
    print("\n[TEST] Fetching 5 posts from r/wallstreetbets...")

    scraper = RedditScraper(timeout=15)
    posts = scraper.fetch_subreddit_posts(
        subreddit="wallstreetbets",
        limit=5,
        category="new",
    )

    assert len(posts) > 0, "Should fetch at least 1 post"
    assert len(posts) <= 5, "Should not exceed limit"

    # Check post structure
    post = posts[0]
    assert "id" in post
    assert "title" in post
    assert "author" in post
    assert "created_utc" in post
    assert "score" in post

    print(f"  -> Fetched {len(posts)} posts")
    print(f"  -> First post: {post['title'][:50]}...")
    return True


def test_scraper_time_filter():
    """Test time window filtering."""
    print("\n[TEST] Testing time window filter (last 1 hour)...")

    scraper = RedditScraper(timeout=15)
    now_ts = int(time.time())
    one_hour_ago = now_ts - 3600

    posts = scraper.fetch_subreddit_posts(
        subreddit="wallstreetbets",
        limit=100,
        category="new",
        since_ts=one_hour_ago,
    )

    # All posts should be within the time window
    for post in posts:
        assert post["created_utc"] >= one_hour_ago, \
            f"Post created_utc {post['created_utc']} < since_ts {one_hour_ago}"

    print(f"  -> Fetched {len(posts)} posts from last hour")
    return True


def test_fetch_posts_function():
    """Test the fetch_posts module function."""
    print("\n[TEST] Testing fetch_posts(hours=1)...")

    posts = fetch_posts(hours=1)

    assert isinstance(posts, list)
    print(f"  -> Fetched {len(posts)} raw posts from all subreddits")

    if posts:
        # Check structure
        post = posts[0]
        assert "id" in post
        assert "title" in post

    return True


def test_fetch_posts_as_models():
    """Test fetching posts as Post model instances."""
    print("\n[TEST] Testing fetch_posts_as_models(hours=1)...")

    posts, count = fetch_posts_as_models(hours=1)

    assert isinstance(posts, list)
    assert count == len(posts)

    print(f"  -> Fetched {count} Post models")

    if posts:
        post = posts[0]
        assert isinstance(post, Post)
        assert post.source == "reddit"
        assert post.source_id
        assert post.content
        assert post.content_hash  # Should be auto-generated

        print(f"  -> Sample post:")
        print(f"     Title: {post.content[:60]}...")
        print(f"     Author: {post.author_name}")
        print(f"     Score: {post.likes}")
        print(f"     Hash: {post.content_hash[:16]}...")

    return True


def test_invalid_hours():
    """Test that invalid hours raises ValueError."""
    print("\n[TEST] Testing invalid hours parameter...")

    try:
        fetch_posts(hours=0)
        assert False, "Should raise ValueError for hours=0"
    except ValueError:
        print("  -> Correctly raised ValueError for hours=0")

    try:
        fetch_posts(hours=-1)
        assert False, "Should raise ValueError for hours=-1"
    except ValueError:
        print("  -> Correctly raised ValueError for hours=-1")

    return True


def run_all_tests():
    """Run all tests and report results."""
    print("=" * 60)
    print("Reddit Collector Test Suite")
    print("=" * 60)
    print(f"Target subreddits: {', '.join(SUBREDDITS)}")

    tests = [
        ("Fetch wallstreetbets", test_scraper_fetch_wallstreetbets),
        ("Time filter", test_scraper_time_filter),
        ("fetch_posts function", test_fetch_posts_function),
        ("fetch_posts_as_models", test_fetch_posts_as_models),
        ("Invalid hours", test_invalid_hours),
    ]

    passed = 0
    failed = 0

    for name, test_fn in tests:
        try:
            result = test_fn()
            if result:
                passed += 1
                print(f"  [PASS] {name}")
            else:
                failed += 1
                print(f"  [FAIL] {name}")
        except Exception as e:
            failed += 1
            print(f"  [FAIL] {name}: {e}")

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
