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
        # Normalize to bytes explicitly
        content_bytes = self.content.encode("utf-8", errors="ignore")
        return sha256(content_bytes).hexdigest()


__all__ = ["Post"]


if __name__ == "__main__":
    # Simple duplicate-set test: two posts with identical content
    sample_content = (
        "Apple releases new iPhone; investors react positively to features."
    )

    post_a = Post(
        source="reddit",
        source_id="r1",
        source_url="https://reddit.com/r/stocks/abc",
        content=sample_content,
        author_id="u123",
        author_name="Alice",
        post_time=1733333333,
        likes=10,
        comments=2,
        shares=1,
    )

    post_b = Post(
        source="twitter",
        source_id="t1",
        source_url="https://twitter.com/user/status/xyz",
        content=sample_content,
        author_id="u456",
        author_name="Bob",
        post_time=1733333399,
        likes=8,
        comments=1,
        shares=0,
    )

    hash_a = post_a.content_hash
    hash_b = post_b.content_hash

    print(f"hash_a={hash_a}")
    print(f"hash_b={hash_b}")
    print(f"equal={hash_a == hash_b}")

    assert hash_a == hash_b, "Content hashes should match for identical content"
    print("Duplicate content hash match: OK")
