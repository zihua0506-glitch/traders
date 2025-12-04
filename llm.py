"""LLM module: structured sentiment analysis with LangChain OpenAI.

Implements Tasks 7-12 from the sentiment collector plan:
- Task 7: `analyze(post: Post)` calls LangChain OpenAI to return a structured
  result: {is_valid, sentiment, tickers, summary}.
- Task 8: Structured output parsing via Pydantic/with_structured_output.
- Task 9: Input cleaning + truncation (MAX_INPUT_CHARS=1200).
- Task 10: Lightweight model and params (gpt-4o-mini, temperature=0,
  max_tokens~120, TIMEOUT_S=10).
- Task 11: Timeout retry exactly once; fallback to a skip marker.
- Task 12: Rule-based prefiltering for obvious non-content (short, links only,
  emojis, ad keywords).

Usage (quick check):
  OPENAI_API_KEY=... python -m llm "Your text here"

This script prints a JSON object with the structured result.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from dataclasses import asdict
from typing import List, Literal, Optional

from models import Post
from config import (
    OPENAI_MODEL,
    TEMPERATURE,
    MAX_TOKENS,
    TIMEOUT_S,
    MAX_INPUT_CHARS,
    OPENAI_API_KEY,
    configure_logging,
    record_llm_latency,
)

try:
    # LangChain for OpenAI chat models and structured output
    from langchain_openai import ChatOpenAI  # type: ignore
    from pydantic import BaseModel, Field
except Exception:  # pragma: no cover
    ChatOpenAI = None  # type: ignore
    BaseModel = object  # type: ignore
    Field = lambda *args, **kwargs: None  # type: ignore


# Logger
logger = logging.getLogger(__name__)


# Config constants imported from centralized config


# Prefilter rules
AD_KEYWORDS = [
    "promo", "discount", "subscribe", "giveaway", "follow", "sale",
    "coupon", "free", "join", "referral", "airdrop", "click", "buy now",
    "sponsored", "affiliate", "use code", "sign up", "offer",
]


class StructuredLLMResult(BaseModel):  # type: ignore[misc]
    """Structured analysis output schema for the LLM response."""

    is_valid: bool = Field(
        description="Whether the post is meaningful for financial analysis",
    )
    sentiment: Literal["bullish", "bearish", "neutral"] = Field(
        description="Overall market sentiment expressed by the post",
        default="neutral",
    )
    tickers: List[str] = Field(
        description="List of stock tickers referenced (uppercase symbols)",
        default_factory=list,
    )
    summary: str = Field(
        description="One-sentence summary of the post for storage",
        default="",
    )


def _strip_fenced_code(text: str) -> str:
    # Remove fenced code blocks ``` ... ``` and inline `code`
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"`[^`\n]+`", " ", text)
    return text


def _remove_long_quotes_and_url_lists(text: str) -> str:
    cleaned_lines: List[str] = []
    url_pat = re.compile(r"https?://\S+", re.IGNORECASE)
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        # Drop long markdown-style quotes
        if line.startswith(">") and len(line) > 60:
            continue
        # Drop pure URL lines or lines containing 2+ URLs (likely a URL list)
        urls = url_pat.findall(line)
        if (urls and url_pat.sub("", line).strip() == "") or len(urls) >= 2:
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


def _truncate(text: str, limit: int = MAX_INPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit]


def _has_meaningful_content(text: str) -> bool:
    # Heuristic: contains at least a few alphanumerics and letters
    # after stripping URLs and emojis.
    t = re.sub(r"https?://\S+", " ", text)
    # remove common emoji ranges
    t = re.sub(r"[\U00010000-\U0010ffff]", " ", t)
    # letters or digits count
    return len(re.findall(r"[A-Za-z0-9]", t)) >= 16


def _looks_like_only_links_or_emojis(text: str) -> bool:
    t = re.sub(r"https?://\S+", " ", text)
    t = re.sub(r"[\U00010000-\U0010ffff]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t == ""


def _contains_ad_keywords(text: str) -> bool:
    lower = text.lower()
    return any(k in lower for k in AD_KEYWORDS)


def _clean_and_prepare_input(content: str) -> str:
    # Step 1: remove code blocks and inline code
    text = _strip_fenced_code(content)
    # Step 2: remove long quotes and url lists
    text = _remove_long_quotes_and_url_lists(text)
    # Step 3: collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    # Step 4: truncate to limit
    text = _truncate(text, MAX_INPUT_CHARS)
    return text


def _build_system_prompt() -> str:
    return (
        "You are a financial social media analysis assistant. "
        "Given a post, determine if it is meaningful for financial analysis, "
        "classify sentiment (bullish/bearish/neutral), extract any mentioned stock tickers "
        "(uppercase symbols like AAPL, TSLA), and provide a concise one-sentence summary. "
        "Be conservative: if unsure, mark neutral and is_valid=false if content has no real substance."
    )


def _invoke_llm(clean_text: str) -> StructuredLLMResult:
    if ChatOpenAI is None:
        raise RuntimeError(
            "langchain_openai is not installed. Install 'langchain' and 'langchain-openai'."
        )

    # LangChain ChatOpenAI client
    client = ChatOpenAI(
        model=OPENAI_MODEL,
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
        timeout=TIMEOUT_S,  # supported in recent langchain-openai
        api_key=OPENAI_API_KEY,
    )

    # Use with_structured_output with our Pydantic model
    structured = client.with_structured_output(StructuredLLMResult)

    # Compose messages: system + user
    messages = [
        ("system", _build_system_prompt()),
        (
            "user",
            (
                "Source: reddit/social\n"
                "Task: Analyze the following post text.\n"
                f"Text: {clean_text}"
            ),
        ),
    ]

    # Call the model; return Pydantic object
    return structured.invoke(messages)  # type: ignore[no-any-return]


def analyze(post: Post) -> dict:
    """Analyze a Post using a lightweight OpenAI chat model via LangChain.

    Returns a dict with keys: is_valid, sentiment, tickers, summary.
    Applies rule-based prefiltering and robust structured parsing.
    """

    # Rule prefilter (Task 12)
    raw_text = post.content or ""
    if not _has_meaningful_content(raw_text) or _looks_like_only_links_or_emojis(raw_text):
        return {
            "is_valid": False,
            "sentiment": "neutral",
            "tickers": [],
            "summary": "",
        }
    if _contains_ad_keywords(raw_text):
        return {
            "is_valid": False,
            "sentiment": "neutral",
            "tickers": [],
            "summary": "",
        }

    # Clean + truncate (Task 9)
    clean_text = _clean_and_prepare_input(raw_text)
    logger.debug(
        "LLM input length after cleaning: %d (sample: %r)",
        len(clean_text), clean_text[:120]
    )

    # Structured LLM call with timeout and single retry on timeout (Tasks 7-11)
    def _default_fallback(summary_note: str) -> dict:
        return {
            "is_valid": False,
            "sentiment": "neutral",
            "tickers": [],
            "summary": summary_note,
        }

    # Safe skip when API key is missing (Task 24)
    if not OPENAI_API_KEY:
        logger.info("OPENAI_API_KEY not set; skipping LLM analysis safely")
        return _default_fallback("[skipped: missing_openai_api_key]")

    # First attempt
    try:
        import time
        _t0 = time.perf_counter()
        result = _invoke_llm(clean_text)
        _t1 = time.perf_counter()
        record_llm_latency(_t1 - _t0, succeeded=True)
        # Convert Pydantic model to dict in a stable shape
        return {
            "is_valid": bool(result.is_valid),
            "sentiment": str(result.sentiment),
            "tickers": [str(t).upper() for t in (result.tickers or [])],
            "summary": str(result.summary or "").strip(),
        }
    except Exception as e:
        msg = str(e).lower()
        is_timeout = "timeout" in msg or "timed out" in msg
        # Record failed attempt latency if available
        try:
            _t1
            _t0
        except NameError:
            _t0 = None
            _t1 = None
        if isinstance(_t0, float) and isinstance(_t1, float) and _t1 >= _t0:
            record_llm_latency(_t1 - _t0, succeeded=False)
        if not is_timeout:
            logger.warning("LLM call failed (non-timeout): %s", e)
            return _default_fallback("[skipped: llm_error]")

    # Retry once for timeouts only
    try:
        import time
        _r0 = time.perf_counter()
        result = _invoke_llm(clean_text)
        _r1 = time.perf_counter()
        record_llm_latency(_r1 - _r0, succeeded=True)
        return {
            "is_valid": bool(result.is_valid),
            "sentiment": str(result.sentiment),
            "tickers": [str(t).upper() for t in (result.tickers or [])],
            "summary": str(result.summary or "").strip(),
        }
    except Exception as e2:
        try:
            _r1
            _r0
        except NameError:
            _r0 = None
            _r1 = None
        if isinstance(_r0, float) and isinstance(_r1, float) and _r1 >= _r0:
            record_llm_latency(_r1 - _r0, succeeded=False)
        logger.warning("LLM timeout retry failed: %s", e2)
        return _default_fallback("[skipped: llm_timeout]")


def _cli_make_post(text: str) -> Post:
    # Create a minimal Post for CLI testing
    return Post(
        source="cli",
        source_id="cli-0",
        source_url="https://example.invalid/cli",
        content=text,
        author_id="cli",
        author_name="cli",
        post_time=0,
        likes=0,
        comments=0,
        shares=0,
    )


def _configure_root_logger() -> None:
    # Delegate to centralized config
    configure_logging()


if __name__ == "__main__":
    _configure_root_logger()
    if len(sys.argv) < 2:
        print("Usage: python -m llm \"<text>\"")
        sys.exit(2)
    text = sys.argv[1]
    post = _cli_make_post(text)
    try:
        result = analyze(post)
    except Exception as exc:
        logger.error("Analysis error: %s", exc, exc_info=True)
        print(json.dumps({
            "is_valid": False,
            "sentiment": "neutral",
            "tickers": [],
            "summary": "[skipped: runtime_error]",
        }))
        sys.exit(1)
    print(json.dumps(result, ensure_ascii=False))


__all__ = ["analyze", "StructuredLLMResult"]
