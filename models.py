"""Core data models for the sentiment collector.

Defines the `Post` dataclass used across collectors, LLM, and DB layers.
The `content_hash` is a derived, deterministic hash based solely on `content`.
"""

from __future__ import annotations

from dataclasses import dataclass
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

    @property
    def content_hash(self) -> str:
        """Stable hexadecimal hash derived only from `content`.

        Uses SHA-256 to ensure determinism across interpreter runs and machines.
        """
        # Normalize to bytes explicitly
        content_bytes = self.content.encode("utf-8", errors="ignore")
        return sha256(content_bytes).hexdigest()


__all__ = ["Post"]

