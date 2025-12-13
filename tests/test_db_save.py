"""Unit test for DB saving.

Run with: python tests/test_db_save.py
Or: python -m pytest tests/test_db_save.py -v
"""

import os
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from playhouse.sqlite_ext import SqliteExtDatabase

import db as dbmod
from models import Post


def use_temp_db(path: str) -> None:
    """Rebind peewee models to a temporary SQLite database file."""
    newdb = SqliteExtDatabase(path, pragmas={
        "journal_mode": "wal",
        "cache_size": -1024 * 16,
        "foreign_keys": 1,
        "ignore_check_constraints": 0,
    })
    # Patch global db and model Meta databases
    dbmod.db = newdb
    dbmod.BaseModel._meta.database = newdb
    dbmod.IndexStock._meta.database = newdb
    dbmod.SentimentPost._meta.database = newdb
    dbmod.XUsername._meta.database = newdb


def test_db_save_post() -> bool:
    """Save a Post and assert it exists in SentimentPost."""
    tmp_db = str(Path(__file__).parent / "test_sentiment.db")
    # Remove any stale file
    try:
        os.remove(tmp_db)
    except Exception:
        pass

    use_temp_db(tmp_db)
    dbmod.init_db()

    post = Post(
        source="x",
        source_id="1234567890",
        source_url="https://x.com/foo/status/1234567890",
        content="Testing DB save pipeline",
        author_id="foo",
        author_name="foo",
        post_time=int(time.time()),
        likes=1,
        comments=2,
        shares=3,
        bookmarks=0,
        views=0,
        images=[],
        video_url="",
        quoted_url="",
        is_retweet=False,
        is_reply=False,
        original_source_id="",
    )

    ok = post.save()
    assert ok, "DB save should succeed"

    exists = dbmod.SentimentModel.exists_source_id("x", "1234567890")
    assert exists, "Row should exist after save"

    return True


def run():
    print("Running DB save test...")
    try:
        assert test_db_save_post()
        print("[PASS] test_db_save_post")
        sys.exit(0)
    except AssertionError as e:
        print(f"[FAIL] {e}")
        sys.exit(1)


if __name__ == "__main__":
    run()
