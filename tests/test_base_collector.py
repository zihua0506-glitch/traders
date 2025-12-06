"""Test cases for BaseCollector and refactored Reddit collector.

Run with: python -m pytest tests/test_base_collector.py -v
Or simply: python tests/test_base_collector.py
"""

import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from collectors.base import BaseCollector, USER_AGENTS
from collectors.reddit import (
    RedditCollector,
    RedditScraper,  # Legacy alias
    fetch_posts,
    fetch_posts_as_models,
    SUBREDDITS,
)
from models import Post


def test_base_collector_user_agents():
    """Test that USER_AGENTS list is populated."""
    print("\n[TEST] Checking USER_AGENTS...")

    assert len(USER_AGENTS) > 0, "USER_AGENTS should not be empty"
    assert all(isinstance(ua, str) for ua in USER_AGENTS)

    print(f"  -> {len(USER_AGENTS)} user agents available")
    return True


def test_reddit_collector_inherits_base():
    """Test that RedditCollector inherits from BaseCollector."""
    print("\n[TEST] Checking RedditCollector inheritance...")

    assert issubclass(RedditCollector, BaseCollector)

    collector = RedditCollector()
    assert hasattr(collector, 'session')
    assert hasattr(collector, 'timeout')
    assert hasattr(collector, 'delay')
    assert hasattr(collector, '_get')
    assert hasattr(collector, '_rate_limit')
    assert hasattr(collector, 'fetch_by_symbol')
    assert hasattr(collector, 'fetch_trending')
    assert hasattr(collector, '_to_post')
    assert hasattr(collector, 'fetch_posts')

    print("  -> RedditCollector correctly inherits BaseCollector")
    return True


def test_reddit_collector_source_name():
    """Test that RedditCollector has correct source_name."""
    print("\n[TEST] Checking source_name...")

    collector = RedditCollector()
    assert collector.source_name == "reddit"

    print(f"  -> source_name = '{collector.source_name}'")
    return True


def test_reddit_collector_session_headers():
    """Test that session has proper headers."""
    print("\n[TEST] Checking session headers...")

    collector = RedditCollector()
    headers = collector.session.headers

    assert "User-Agent" in headers
    assert headers["User-Agent"] in USER_AGENTS
    assert "Accept" in headers

    print(f"  -> User-Agent: {headers['User-Agent'][:50]}...")
    print(f"  -> Accept: {headers['Accept']}")
    return True


def test_legacy_alias():
    """Test that RedditScraper alias works."""
    print("\n[TEST] Checking legacy alias RedditScraper...")

    assert RedditScraper is RedditCollector

    scraper = RedditScraper()
    assert isinstance(scraper, RedditCollector)
    assert isinstance(scraper, BaseCollector)

    print("  -> RedditScraper alias works correctly")
    return True


def test_fetch_trending():
    """Test fetch_trending method."""
    print("\n[TEST] Testing fetch_trending (limit=5)...")

    collector = RedditCollector()
    posts = collector.fetch_trending(limit=5, since_ts=0)

    assert isinstance(posts, list)
    assert len(posts) <= 5

    if posts:
        post = posts[0]
        assert "id" in post
        assert "title" in post
        assert "author" in post
        assert "created_utc" in post
        print(f"  -> Fetched {len(posts)} posts")
        print(f"  -> Sample: {post['title'][:50]}...")
    else:
        print("  -> No posts fetched (may be rate limited)")

    return True


def test_to_post_conversion():
    """Test _to_post converts raw data to Post model."""
    print("\n[TEST] Testing _to_post conversion...")

    collector = RedditCollector()

    raw = {
        "id": "test123",
        "title": "Test Post Title",
        "selftext": "Test post body content",
        "author": "test_user",
        "permalink": "/r/stocks/comments/test123/test_post/",
        "score": 42,
        "num_comments": 10,
        "created_utc": int(time.time()),
    }

    post = collector._to_post(raw)

    assert isinstance(post, Post)
    assert post.source == "reddit"
    assert post.source_id == "test123"
    assert "Test Post Title" in post.content
    assert "Test post body content" in post.content
    assert post.author_name == "test_user"
    assert post.likes == 42
    assert post.comments == 10
    assert post.source_url.startswith("https://www.reddit.com")
    assert post.content_hash  # Should be auto-generated

    print(f"  -> Converted to Post model successfully")
    print(f"  -> source_url: {post.source_url}")
    print(f"  -> content_hash: {post.content_hash[:16]}...")
    return True


def test_fetch_posts_unified_interface():
    """Test the unified fetch_posts method."""
    print("\n[TEST] Testing unified fetch_posts interface...")

    collector = RedditCollector()
    posts, count = collector.fetch_posts(hours=1, limit=5)

    assert isinstance(posts, list)
    assert isinstance(count, int)
    assert count == len(posts)

    if posts:
        assert all(isinstance(p, Post) for p in posts)
        assert all(p.source == "reddit" for p in posts)
        print(f"  -> Fetched {count} Post models via unified interface")
    else:
        print("  -> No posts fetched (may be rate limited)")

    return True


def test_fetch_posts_as_models_function():
    """Test module-level fetch_posts_as_models function."""
    print("\n[TEST] Testing fetch_posts_as_models function...")

    posts, count = fetch_posts_as_models(hours=1)

    assert isinstance(posts, list)
    assert isinstance(count, int)
    assert count == len(posts)

    print(f"  -> Module function returned {count} posts")
    return True


def test_invalid_hours():
    """Test that invalid hours raises ValueError."""
    print("\n[TEST] Testing invalid hours parameter...")

    collector = RedditCollector()

    try:
        collector.fetch_posts(hours=0)
        assert False, "Should raise ValueError for hours=0"
    except ValueError:
        print("  -> Correctly raised ValueError for hours=0")

    try:
        collector.fetch_posts(hours=-1)
        assert False, "Should raise ValueError for hours=-1"
    except ValueError:
        print("  -> Correctly raised ValueError for hours=-1")

    return True


def run_all_tests():
    """Run all tests and report results."""
    print("=" * 60)
    print("Phase 1 Test Suite: BaseCollector & Reddit Refactor")
    print("=" * 60)

    tests = [
        ("USER_AGENTS check", test_base_collector_user_agents),
        ("Inheritance check", test_reddit_collector_inherits_base),
        ("source_name check", test_reddit_collector_source_name),
        ("Session headers check", test_reddit_collector_session_headers),
        ("Legacy alias check", test_legacy_alias),
        ("fetch_trending method", test_fetch_trending),
        ("_to_post conversion", test_to_post_conversion),
        ("Unified fetch_posts", test_fetch_posts_unified_interface),
        ("Module function", test_fetch_posts_as_models_function),
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
