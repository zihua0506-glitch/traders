"""Sentiment collector main pipeline.

Collects posts from multiple sources (Reddit, Yahoo Finance, Finviz),
analyzes sentiment via LLM, and stores in SQLite.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from typing import Dict, List, Optional, Tuple

from collectors import fetch_all_sources, WORKING_COLLECTORS, COLLECTORS
from llm import analyze
from db import save_post, exists_content_hash
from models import Post
from config import (
    MAX_PARALLEL_LLM,
    configure_logging,
    perf_start_sample,
    get_perf_stats,
)


logger = logging.getLogger(__name__)


def _configure_root_logger() -> None:
    configure_logging()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect posts from social/news sources, analyze sentiment via LLM, and store in SQLite."
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="Time window in hours to collect posts (default: 24)",
    )
    parser.add_argument(
        "--source",
        choices=list(COLLECTORS.keys()) + ["all"],
        default="all",
        help="Data source to collect from (default: all working sources)",
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        help="Stock symbols to fetch (default: trending/general)",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip LLM analysis (collect only)",
    )
    return parser.parse_args()


async def _run_llm_with_limit(posts: List[Post]) -> List[Tuple[Post, Optional[dict]]]:
    """Run LLM analysis concurrently with a semaphore limit.

    Returns list of (post, result_or_none). `None` indicates error/failure.
    """

    sem = asyncio.Semaphore(MAX_PARALLEL_LLM)
    loop = asyncio.get_running_loop()

    async def _task(post: Post) -> Tuple[Post, Optional[dict]]:
        await sem.acquire()
        try:
            result = await loop.run_in_executor(None, analyze, post)
            return post, result
        except Exception as exc:
            logger.warning("LLM analyze failed: %s", exc, exc_info=True)
            return post, None
        finally:
            sem.release()

    tasks = [_task(p) for p in posts]
    return await asyncio.gather(*tasks)


def main() -> int:
    args = _parse_args()
    _configure_root_logger()

    # Determine sources to collect from
    if args.source == "all":
        sources = WORKING_COLLECTORS
    else:
        sources = [args.source]

    # Collect from all sources
    print("=" * 60)
    print("Sentiment Collector")
    print("=" * 60)
    print(f"Sources: {sources}")
    print(f"Hours: {args.hours}")
    print(f"Symbols: {args.symbols or 'trending'}")
    print("-" * 60)

    all_posts: List[Post] = []
    source_stats: Dict[str, int] = {}

    results = fetch_all_sources(hours=args.hours, sources=sources, symbols=args.symbols)

    for source, (posts, count) in results.items():
        source_stats[source] = count
        all_posts.extend(posts)
        logger.info("Collected from %s: %d posts", source, count)

    total_collected = len(all_posts)
    print(f"\nCollected: {total_collected} posts total")
    for source, count in source_stats.items():
        print(f"  - {source}: {count}")

    if args.no_llm:
        print("\n[--no-llm] Skipping LLM analysis")
        print("=" * 60)
        return 0

    # Pre-dedupe before LLM
    to_analyze: List[Post] = []
    skipped_dupes = 0
    for p in all_posts:
        try:
            if exists_content_hash(p.content_hash):
                skipped_dupes += 1
                continue
            to_analyze.append(p)
        except Exception as exc:
            logger.warning("exists_content_hash error: %s", exc, exc_info=True)
            to_analyze.append(p)

    print(f"\nPre-dedupe: {skipped_dupes} duplicates skipped")
    print(f"To analyze: {len(to_analyze)} posts")

    if not to_analyze:
        print("\nNo new posts to analyze.")
        print("=" * 60)
        return 0

    # LLM analysis with concurrency control
    print(f"\nRunning LLM analysis (concurrency={MAX_PARALLEL_LLM})...")

    saved_ok = 0
    analyzed_count = 0

    perf_start_sample(limit=min(300, len(to_analyze)))

    try:
        results = asyncio.run(_run_llm_with_limit(to_analyze))
    except Exception as exc:
        logger.error("LLM batch run failed: %s", exc, exc_info=True)
        results = []

    # Save results
    for post, result in results:
        analyzed_count += 1
        if not result:
            continue
        try:
            if not result.get("is_valid"):
                continue
            ok = save_post(
                post,
                sentiment=str(result.get("sentiment", "neutral")),
                tickers=list(result.get("tickers", [])),
                summary=str(result.get("summary", "")),
            )
            if ok:
                saved_ok += 1
        except Exception as exc:
            logger.warning("DB save failed: %s", exc, exc_info=True)
            continue

    # Summary
    print("\n" + "-" * 60)
    print("Summary:")
    print(f"  Collected: {total_collected}")
    print(f"  Duplicates skipped: {skipped_dupes}")
    print(f"  Analyzed: {analyzed_count}")
    print(f"  Saved: {saved_ok}")

    # Per-source breakdown
    print("\nPer source:")
    for source, count in source_stats.items():
        print(f"  - {source}: {count} collected")

    # Performance stats
    stats = get_perf_stats()
    if stats.get("attempts", 0) > 0:
        print("\nPerformance:")
        print(f"  Avg latency: {stats['avg_latency_s']:.2f}s")
        print(f"  Total time: {stats['total_wall_time_s']:.2f}s")
        print(f"  Attempts: {int(stats['attempts'])}")
        print(f"  Failure ratio: {stats['failure_ratio']:.2%}")

    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
