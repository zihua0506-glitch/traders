"""Core data models for the sentiment collector.

Defines the `Post` dataclass used across collectors, LLM, and DB layers.
The `content_hash` is a derived, deterministic hash based solely on `content`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256


@dataclass
class Post:
    """Social post normalized structure.

    Fields mirror the design spec and are intentionally minimal. The
    `content_hash` is derived from `content` only, ensuring identical content
    produces the same hash across sources and runs.
    """

    # Source metadata
    source: str
    source_id: str
    source_url: str

    # Content and author
    content: str
    author_id: str
    author_name: str

    # Timestamps and engagement
    post_time: int  # Unix timestamp (seconds)
    likes: int = 0
    comments: int = 0
    shares: int = 0

    # Extended media and relation fields
    bookmarks: int = 0
    views: int = 0
    images: list[str] = field(default_factory=list)
    video_url: str = ""
    quoted_url: str = ""
    is_retweet: bool = False
    is_reply: bool = False
    original_source_id: str = ""

    # Optional extended metadata (non-persisted or partially persisted)
    region: str = ""
    is_pinned: bool = False
    is_ad: bool = False
    mentions: list[str] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)
    video_duration: str = ""
    is_text_truncated: bool = False

    @property
    def content_hash(self) -> str:
        """Stable hexadecimal hash derived only from `content`.

        Uses SHA-256 to ensure determinism across interpreter runs and machines.
        """
        content_bytes = self.content.encode("utf-8", errors="ignore")
        return sha256(content_bytes).hexdigest()

    def save(self, sentiment: str = "neutral", tickers: list[str] | None = None, summary: str = "") -> bool:
        """Persist this post into the SQLite database via the DB facade.

        Returns True on success, False on unique conflicts or insert failure.
        """
        if tickers is None:
            tickers = []
        try:
            # Lazy import to avoid circular import at module load time
            from db import SentimentModel
        except Exception as e:
            raise RuntimeError("DB layer unavailable for saving Post") from e
        return SentimentModel.save(self, sentiment=sentiment, tickers=tickers, summary=summary)


__all__ = ["Post"]

