"""X (Twitter) username ORM model and helpers."""

from __future__ import annotations

from typing import List

from peewee import AutoField, CharField, BooleanField

from .base import BaseModel


class XUsername(BaseModel):
    """Table storing X (Twitter) usernames to collect."""

    id = AutoField()
    username = CharField(max_length=64, unique=True, index=True)
    enabled = BooleanField(default=True)


def get_enabled_x_usernames() -> List[str]:
    """Return all enabled X usernames (enabled = True)."""
    q = (
        XUsername.select(XUsername.username)
        .where(XUsername.enabled == True)  # noqa: E712
        .order_by(XUsername.username)
    )
    return [row.username for row in q]


__all__ = ["XUsername", "get_enabled_x_usernames"]

