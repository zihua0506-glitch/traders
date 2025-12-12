"""Collectors package.

Provides data collectors for various financial data sources.
"""

from typing import Dict, List, Tuple, Optional

from models import Post

# Import collectors
from .base import BaseCollector
from .reddit import (
    RedditCollector,
    fetch_posts_as_models as fetch_reddit,
    SUBREDDITS,
)
from .stocktwits import (
    StockTwitsCollector,
    fetch_posts_as_models as fetch_stocktwits,
)
from .yahoo import (
    YahooFinanceCollector,
    fetch_posts_as_models as fetch_yahoo,
)
from .finviz import (
    FinvizCollector,
    fetch_posts_as_models as fetch_finviz,
)
try:
    from .x_scraper import XScraperCollector  # optional; may be absent
except Exception:
    XScraperCollector = None

# Registry of available collectors
COLLECTORS = {
    "reddit": fetch_reddit,
    "stocktwits": fetch_stocktwits,
    "yahoo": fetch_yahoo,
    "finviz": fetch_finviz,
}

# Collectors that are known to work
WORKING_COLLECTORS = ["reddit", "yahoo", "finviz"]


def fetch_all_sources(
    hours: int,
    sources: Optional[List[str]] = None,
    symbols: Optional[List[str]] = None,
) -> Dict[str, Tuple[List[Post], int]]:
    """Fetch posts from multiple sources.

    Args:
        hours: Time window in hours
        sources: List of source names (default: all working collectors)
        symbols: List of stock symbols (None for trending)

    Returns:
        Dict mapping source name to (posts, count) tuple
    """
    if sources is None:
        sources = WORKING_COLLECTORS

    results = {}
    for source in sources:
        if source not in COLLECTORS:
            continue

        try:
            fetch_func = COLLECTORS[source]
            posts, count = fetch_func(hours=hours, symbols=symbols)
            results[source] = (posts, count)
        except Exception as e:
            results[source] = ([], 0)

    return results


__all__ = [
    "BaseCollector",
    "RedditCollector",
    "StockTwitsCollector",
    "YahooFinanceCollector",
    "FinvizCollector",
    "XScraperCollector",
    "COLLECTORS",
    "WORKING_COLLECTORS",
    "fetch_all_sources",
    "fetch_reddit",
    "fetch_stocktwits",
    "fetch_yahoo",
    "fetch_finviz",
]
