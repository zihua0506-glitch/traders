"""Test cases for all collectors.

Run with: python -m pytest tests/test_collectors.py -v
Or simply: python tests/test_collectors.py
"""

import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models import Post
from collectors import (
    BaseCollector,
    RedditCollector,
    YahooFinanceCollector,
    FinvizCollector,
    StockTwitsCollector,
    COLLECTORS,
    WORKING_COLLECTORS,
    fetch_all_sources,
)


# =============================================================================
# BaseCollector Tests
# =============================================================================

def test_base_collector_is_abstract():
    """Test that BaseCollector cannot be instantiated directly."""
    print("\n[TEST] BaseCollector is abstract...")

    try:
        BaseCollector()
        assert False, "Should not be able to instantiate BaseCollector"
    except TypeError:
        print("  -> Correctly raises TypeError")

    return True


# =============================================================================
# Reddit Collector Tests
# =============================================================================

def test_reddit_collector_inheritance():
    """Test RedditCollector inherits from BaseCollector."""
    print("\n[TEST] RedditCollector inheritance...")

    assert issubclass(RedditCollector, BaseCollector)
    collector = RedditCollector()
    assert collector.source_name == "reddit"

    print("  -> RedditCollector inherits BaseCollector correctly")
    return True


def test_reddit_fetch_trending():
    """Test Reddit fetch_trending."""
    print("\n[TEST] Reddit fetch_trending...")

    collector = RedditCollector()
    posts = collector.fetch_trending(limit=3, since_ts=0)

    assert isinstance(posts, list)
    if posts:
        assert "id" in posts[0]
        assert "title" in posts[0]
        print(f"  -> Fetched {len(posts)} posts")
    else:
        print("  -> No posts (may be rate limited)")

    return True


def test_reddit_to_post():
    """Test Reddit _to_post conversion."""
    print("\n[TEST] Reddit _to_post conversion...")

    collector = RedditCollector()
    raw = {
        "id": "test123",
        "title": "Test Title",
        "selftext": "Test body",
        "author": "testuser",
        "permalink": "/r/stocks/test123",
        "score": 100,
        "num_comments": 50,
        "created_utc": int(time.time()),
    }

    post = collector._to_post(raw)

    assert isinstance(post, Post)
    assert post.source == "reddit"
    assert post.source_id == "test123"
    assert "Test Title" in post.content
    assert post.author_name == "testuser"
    assert post.likes == 100

    print("  -> Conversion successful")
    return True


# =============================================================================
# Yahoo Finance Collector Tests
# =============================================================================

def test_yahoo_collector_inheritance():
    """Test YahooFinanceCollector inherits from BaseCollector."""
    print("\n[TEST] YahooFinanceCollector inheritance...")

    assert issubclass(YahooFinanceCollector, BaseCollector)
    collector = YahooFinanceCollector()
    assert collector.source_name == "yahoo"

    print("  -> YahooFinanceCollector inherits BaseCollector correctly")
    return True


def test_yahoo_fetch_by_symbol():
    """Test Yahoo Finance fetch_by_symbol."""
    print("\n[TEST] Yahoo fetch_by_symbol (AAPL)...")

    collector = YahooFinanceCollector()
    news = collector.fetch_by_symbol("AAPL", limit=3, since_ts=0)

    assert isinstance(news, list)
    if news:
        assert "title" in news[0]
        assert "link" in news[0]
        print(f"  -> Fetched {len(news)} news items")
        print(f"  -> Sample: {news[0]['title'][:50]}...")
    else:
        print("  -> No news items")

    return True


def test_yahoo_to_post():
    """Test Yahoo _to_post conversion."""
    print("\n[TEST] Yahoo _to_post conversion...")

    collector = YahooFinanceCollector()
    raw = {
        "title": "Test News Title",
        "link": "https://finance.yahoo.com/news/test",
        "summary": "Test summary",
        "source": "Reuters",
        "published": int(time.time()),
    }

    post = collector._to_post(raw)

    assert isinstance(post, Post)
    assert post.source == "yahoo"
    assert "Test News Title" in post.content
    assert post.author_name == "Reuters"

    print("  -> Conversion successful")
    return True


# =============================================================================
# Finviz Collector Tests
# =============================================================================

def test_finviz_collector_inheritance():
    """Test FinvizCollector inherits from BaseCollector."""
    print("\n[TEST] FinvizCollector inheritance...")

    assert issubclass(FinvizCollector, BaseCollector)
    collector = FinvizCollector()
    assert collector.source_name == "finviz"

    print("  -> FinvizCollector inherits BaseCollector correctly")
    return True


def test_finviz_fetch_by_symbol():
    """Test Finviz fetch_by_symbol."""
    print("\n[TEST] Finviz fetch_by_symbol (AAPL)...")

    collector = FinvizCollector()
    news = collector.fetch_by_symbol("AAPL", limit=3, since_ts=0)

    assert isinstance(news, list)
    if news:
        assert "title" in news[0]
        assert "link" in news[0]
        print(f"  -> Fetched {len(news)} news items")
        print(f"  -> Sample: {news[0]['title'][:50]}...")
    else:
        print("  -> No news items")

    return True


def test_finviz_time_parsing():
    """Test Finviz time parsing."""
    print("\n[TEST] Finviz time parsing...")

    collector = FinvizCollector()

    # Full date format
    ts1 = collector._parse_finviz_time("Dec-05-24 10:30AM", None)
    assert ts1 > 0, "Full date parsing failed"

    # Time only with base date
    ts2 = collector._parse_finviz_time("10:30AM", "Dec-05-24")
    assert ts2 > 0, "Time-only parsing failed"

    print(f"  -> Full date: {ts1}")
    print(f"  -> Time only: {ts2}")
    return True


def test_finviz_to_post():
    """Test Finviz _to_post conversion."""
    print("\n[TEST] Finviz _to_post conversion...")

    collector = FinvizCollector()
    raw = {
        "title": "Test News Title",
        "link": "https://example.com/news",
        "source": "Benzinga",
        "published": int(time.time()),
    }

    post = collector._to_post(raw)

    assert isinstance(post, Post)
    assert post.source == "finviz"
    assert post.content == "Test News Title"
    assert post.author_name == "Benzinga"

    print("  -> Conversion successful")
    return True


# =============================================================================
# StockTwits Collector Tests
# =============================================================================

def test_stocktwits_collector_inheritance():
    """Test StockTwitsCollector inherits from BaseCollector."""
    print("\n[TEST] StockTwitsCollector inheritance...")

    assert issubclass(StockTwitsCollector, BaseCollector)
    collector = StockTwitsCollector()
    assert collector.source_name == "stocktwits"

    print("  -> StockTwitsCollector inherits BaseCollector correctly")
    print("  -> NOTE: StockTwits blocked by Cloudflare, API calls will fail")
    return True


# =============================================================================
# Integration Tests
# =============================================================================

def test_collectors_registry():
    """Test COLLECTORS registry."""
    print("\n[TEST] COLLECTORS registry...")

    assert "reddit" in COLLECTORS
    assert "yahoo" in COLLECTORS
    assert "finviz" in COLLECTORS
    assert "stocktwits" in COLLECTORS

    print(f"  -> Registered collectors: {list(COLLECTORS.keys())}")
    return True


def test_working_collectors_list():
    """Test WORKING_COLLECTORS list."""
    print("\n[TEST] WORKING_COLLECTORS list...")

    assert "reddit" in WORKING_COLLECTORS
    assert "yahoo" in WORKING_COLLECTORS
    assert "finviz" in WORKING_COLLECTORS
    # StockTwits should NOT be in working collectors
    assert "stocktwits" not in WORKING_COLLECTORS

    print(f"  -> Working collectors: {WORKING_COLLECTORS}")
    return True


def test_fetch_all_sources():
    """Test fetch_all_sources integration."""
    print("\n[TEST] fetch_all_sources (yahoo only, limit test)...")

    results = fetch_all_sources(hours=24, sources=["yahoo"])

    assert "yahoo" in results
    posts, count = results["yahoo"]
    assert isinstance(posts, list)
    assert isinstance(count, int)

    print(f"  -> Yahoo: {count} posts")
    return True


def test_unified_fetch_posts_interface():
    """Test unified fetch_posts interface across collectors."""
    print("\n[TEST] Unified fetch_posts interface...")

    collectors = [
        ("reddit", RedditCollector()),
        ("yahoo", YahooFinanceCollector()),
        ("finviz", FinvizCollector()),
    ]

    for name, collector in collectors:
        posts, count = collector.fetch_posts(hours=1, limit=2)
        assert isinstance(posts, list)
        assert isinstance(count, int)
        assert count == len(posts)

        if posts:
            assert all(isinstance(p, Post) for p in posts)
            assert all(p.source == name for p in posts)

        print(f"  -> {name}: {count} posts")

    return True


# =============================================================================
# Test Runner
# =============================================================================

def run_all_tests():
    """Run all tests and report results."""
    print("=" * 60)
    print("Multi-Platform Collectors Test Suite")
    print("=" * 60)

    tests = [
        # Base
        ("BaseCollector is abstract", test_base_collector_is_abstract),

        # Reddit
        ("Reddit inheritance", test_reddit_collector_inheritance),
        ("Reddit fetch_trending", test_reddit_fetch_trending),
        ("Reddit _to_post", test_reddit_to_post),

        # Yahoo
        ("Yahoo inheritance", test_yahoo_collector_inheritance),
        ("Yahoo fetch_by_symbol", test_yahoo_fetch_by_symbol),
        ("Yahoo _to_post", test_yahoo_to_post),

        # Finviz
        ("Finviz inheritance", test_finviz_collector_inheritance),
        ("Finviz fetch_by_symbol", test_finviz_fetch_by_symbol),
        ("Finviz time parsing", test_finviz_time_parsing),
        ("Finviz _to_post", test_finviz_to_post),

        # StockTwits
        ("StockTwits inheritance", test_stocktwits_collector_inheritance),

        # Integration
        ("COLLECTORS registry", test_collectors_registry),
        ("WORKING_COLLECTORS list", test_working_collectors_list),
        ("fetch_all_sources", test_fetch_all_sources),
        ("Unified fetch_posts", test_unified_fetch_posts_interface),
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
