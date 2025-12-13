"""Database base module.

Holds the Sqlite database connection and BaseModel for Peewee ORM.
Other business models should import `db` and `BaseModel` from here.
"""

from __future__ import annotations

from playhouse.sqlite_ext import SqliteExtDatabase
from peewee import Model

# Database file in the project root; simple and portable for MVP.
DB_FILE = "sentiment.db"

db = SqliteExtDatabase(
    DB_FILE,
    pragmas={
        "journal_mode": "wal",
        "cache_size": -1024 * 64,  # 64MB page cache
        "foreign_keys": 1,
        "ignore_check_constraints": 0,
    },
)


class BaseModel(Model):
    class Meta:
        database = db


__all__ = ["db", "BaseModel", "DB_FILE"]

