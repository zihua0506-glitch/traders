"""Sentiment collector main pipeline.

Implements Tasks 17-22:
- Parse CLI arg `--hours` with default 24 (argparse)
- Collect posts and accumulate total counts per data source (Reddit)
- Pre-dedupe before LLM via `exists_content_hash`
- Controlled LLM concurrency (`MAX_PARALLEL_LLM=8`) using asyncio + semaphore
- Robust error handling: log and continue on failures/timeouts
- Summary stats: per source collected/inserted counts printed at end

This integrates collectors.reddit, llm, and db modules per the design.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from typing import Dict, List, Optional, Tuple

from collectors.reddit import fetch_posts_as_models
from llm import analyze
from db import save_post, exists_content_hash
from models import Post


# Constants
MAX_PARALLEL_LLM = 8


logger = logging.getLogger(__name__)


def _configure_root_logger() -> None:
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Collect recent Reddit posts, analyze sentiment via LLM, and store in SQLite."
        )
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="Time window in hours to collect posts (default: 24)",
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
            # Offload blocking LLM call to thread pool to avoid blocking event loop
            result = await loop.run_in_executor(None, analyze, post)
            return post, result
        except Exception as exc:
            logger.warning("LLM analyze failed: %s", exc, exc_info=True)
            return post, None
        finally:
            sem.release()

    tasks = [_task(p) for p in posts]
    # Gather with return_exceptions=False; individual task handles its own errors
    return await asyncio.gather(*tasks)


def main() -> int:
    args = _parse_args()
    _configure_root_logger()

    # Collector: Reddit
    try:
        reddit_posts, reddit_collected = fetch_posts_as_models(args.hours)
    except Exception as exc:
        logger.error("Reddit collection failed: %s", exc, exc_info=True)
        reddit_posts, reddit_collected = [], 0

    logger.info("Collected from reddit: %d posts (within %d hours)", reddit_collected, args.hours)

    # Pre-dedupe before LLM: skip posts whose content_hash already exists
    to_analyze: List[Post] = []
    skipped_dupes = 0
    for p in reddit_posts:
        try:
            if exists_content_hash(p.content_hash):
                skipped_dupes += 1
                continue
            to_analyze.append(p)
        except Exception as exc:
            # Defensive: existence check error should not break pipeline
            logger.warning("exists_content_hash error: %s", exc, exc_info=True)
            # fall back to analyzing; better to try than drop completely
            to_analyze.append(p)

    logger.info("Pre-dedupe skipped existing: %d", skipped_dupes)

    # Controlled concurrency LLM
    saved_ok = 0
    analyzed_count = 0

    if to_analyze:
        try:
            results = asyncio.run(_run_llm_with_limit(to_analyze))
        except Exception as exc:
            logger.error("LLM batch run failed: %s", exc, exc_info=True)
            results = []

        # Save sequentially to avoid SQLite thread issues
        for post, result in results:
            analyzed_count += 1
            if not result:
                # Analysis error/timeout already logged; skip storage
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

    # Stats output per data source (reddit only in MVP)
    print("Summary:")
    print(f"  reddit: collected={reddit_collected}, dedupe_skipped={skipped_dupes}, analyzed={analyzed_count}, saved={saved_ok}")
    total_collected = reddit_collected
    total_saved = saved_ok
    print(f"  total: collected={total_collected}, saved={total_saved}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
