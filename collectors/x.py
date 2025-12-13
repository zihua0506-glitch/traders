from typing import Optional, List, Dict, Any, Tuple
import re
import subprocess
import time
import urllib.request
import json
from datetime import datetime

import os
import logging
from dotenv import load_dotenv
from playwright.sync_api import (
    sync_playwright,
    TimeoutError as PlaywrightTimeoutError,
    Page,
    ElementHandle,
    Playwright,
)

from models import Post
from db import SentimentModel
from collectors.base import BaseCollector
from models.x_username import get_enabled_x_usernames
from llm import analyze as llm_analyze


def _login_x(p: Playwright, cdp_url: Optional[str] = None, headless: bool = False) -> None:
    """Login to X (Twitter) by reusing an existing Playwright instance and CDP.

    This function avoids creating a nested `sync_playwright()` context, which
    would conflict with the active Playwright event loop. Instead, callers must
    pass the current `Playwright` instance. The CDP URL is taken from env
    `X_CDP_URL` unless explicitly provided.

    Environment variables:
      - `play_wright_profile_path` (required)
      - `X_USERNAME`, `X_PASSWORD` (required)
      - `X_EMAIL` (optional)
      - `X_CDP_URL` (optional, default `http://localhost:9222`)
    """

    load_dotenv()
    profile_dir = os.getenv("play_wright_profile_path")
    username = os.getenv("X_USERNAME")
    password = os.getenv("X_PASSWORD")
    email = os.getenv("X_EMAIL")
    cdp = cdp_url or os.getenv("X_CDP_URL", "http://localhost:9222")

    if not profile_dir:
        raise RuntimeError("Environment variable 'play_wright_profile_path' is required")
    if not username or not password:
        raise RuntimeError("Environment variables 'X_USERNAME' and 'X_PASSWORD' are required")

    # Connect to already-running Chrome via CDP using the provided Playwright
    try:
        browser = p.chromium.connect_over_cdp(cdp)
    except Exception as e:
        raise RuntimeError(f"Failed to connect over CDP at {cdp}: {e}")

    if not browser.contexts:
        browser.close()
        raise RuntimeError("No browser contexts available via CDP. Ensure Chrome was launched with user-data-dir.")
    context = browser.contexts[0]
    context.set_default_timeout(30000)
    page = context.new_page()

    # If already logged in (cookies present), short-circuit
    try:
        page.goto("https://x.com/home", wait_until="domcontentloaded")
        if _has_auth_cookies(context):
            browser.close()
            return
    except Exception:
        pass

    # Login flow
    page.goto("https://x.com/i/flow/login", wait_until="domcontentloaded")

    user_input = page.locator('input[name="text"]').first
    user_input.wait_for(state="visible", timeout=30000)
    user_input.fill(username)

    next_btn = page.get_by_role("button", name=re.compile("Next", re.I))
    if next_btn.count() > 0:
        next_btn.first.click()
    else:
        page.locator('div[role="button"]:has-text("Next")').first.click()

    # Some flows ask for email/phone after username. If another text input appears, fill it.
    secondary = page.locator('input[name="text"]').first
    try:
        secondary.wait_for(state="visible", timeout=5000)
        secondary.fill(email or username)
        next2 = page.get_by_role("button", name=re.compile("Next", re.I))
        (next2.first if next2.count() > 0 else page.locator('div[role="button"]:has-text("Next")').first).click()
    except Exception:
        pass

    pw_input = page.locator('input[name="password"]').first
    pw_input.wait_for(state="visible", timeout=30000)
    pw_input.fill(password)

    login_btn = page.get_by_role("button", name=re.compile("Log in", re.I))
    if login_btn.count() > 0:
        login_btn.first.click()
    else:
        page.locator('div[role="button"]:has-text("Log in")').first.click()

    # Wait up to 30s for auth cookies to appear
    deadline = time.time() + 30
    while time.time() < deadline:
        if _has_auth_cookies(context):
            break
        page.wait_for_timeout(1000)
    if not _has_auth_cookies(context):
        browser.close()
        raise RuntimeError("Login appears incomplete (auth cookies missing)")

    browser.close()


def _has_auth_cookies(context) -> bool:
    """Check for presence of typical X auth cookies (auth_token, ct0)."""
    try:
        cookies = context.cookies()
        for c in cookies:
            name = c.get("name")
            domain = c.get("domain", "")
            if name in ("auth_token", "ct0") and ("x.com" in domain or "twitter.com" in domain or domain.startswith(".")):
                return True
        return False
    except Exception:
        return False


# Chrome launch helper is now provided in BaseCollector


# No additional failure detection; keep logic minimal.


# ===== Helpers ported from spec (sync API) =====
_COMPACT_NUM_RE = re.compile(r"^([0-9]+(?:\.[0-9]+)?)([KMB])?$", re.IGNORECASE)
_MENTION_RE = re.compile(r"@[\w]+")
_URL_RE = re.compile(r"https?://[^\s]+")
_GROUP_COUNTS_RE = re.compile(
    r"(\d+)\s*replies.*?(\d+)\s*reposts.*?(\d+)\s*likes.*?(\d+)\s*bookmarks.*?(\d+)\s*views",
    re.IGNORECASE,
)

_MULTIPLIERS = {
    "K": 1_000,
    "M": 1_000_000,
    "B": 1_000_000_000,
}


def _parse_compact_number(s: Optional[str]) -> Optional[int]:
    """Parse numbers like '1.1K', '6.1M', '123' into int or None.

    Robust to labels like 'Views 1,234' or '1,234 views'. Avoids recursion.
    """
    if not s:
        return None
    s_norm = s.strip().replace(",", "")

    # Direct match
    m = _COMPACT_NUM_RE.match(s_norm)
    if m:
        num, suffix = m.groups()
        value = float(num)
        if suffix:
            value *= _MULTIPLIERS.get(suffix.upper(), 1)
        return int(value)

    # Try tokens (prefer last token to catch 'Views 123')
    tokens = s_norm.split()
    for tok in reversed(tokens):
        m = _COMPACT_NUM_RE.match(tok)
        if m:
            num, suffix = m.groups()
            value = float(num)
            if suffix:
                value *= _MULTIPLIERS.get(suffix.upper(), 1)
            return int(value)

    # Fallback: find any number-like pattern within the string
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)([KMB])?", s_norm, re.IGNORECASE)
    if m:
        num, suffix = m.groups()
        value = float(num)
        if suffix:
            value *= _MULTIPLIERS.get(suffix.upper(), 1)
        return int(value)

    return None


def _extract_mentions(text: str) -> List[str]:
    return _MENTION_RE.findall(text) if text else []


def _extract_urls(text: str) -> List[str]:
    return _URL_RE.findall(text) if text else []


def _is_ad_tweet(article: ElementHandle) -> bool:
    text = article.inner_text()
    lines = text.split("\n")
    for line in lines[:10]:
        if line.strip() == "Ad":
            return True
    return False


def _get_repost_info(article: ElementHandle) -> Tuple[bool, Optional[str]]:
    text = article.inner_text()
    m = re.match(r"^(.+?)\s+reposted", text, re.IGNORECASE)
    if m:
        return True, m.group(1).strip()
    return False, None


def _get_region_and_pinned(article: ElementHandle) -> Tuple[str, bool]:
    region = article.evaluate(
        """
        (el) => {
            let node = el;
            while (node) {
                if (node.getAttribute && node.getAttribute('role') === 'region') {
                    const h = node.querySelector('h1,h2,h3');
                    if (h && h.textContent) return h.textContent.trim();
                    const name = node.getAttribute('aria-label');
                    if (name) return name.trim();
                    return 'Unknown region';
                }
                node = node.parentElement;
            }
            return 'Unknown region';
        }
        """
    )
    text = article.inner_text()
    is_pinned = bool(re.match(r"^Pinned\s", text, re.IGNORECASE))
    return region or "Unknown region", is_pinned


def _check_text_truncated(article: ElementHandle) -> bool:
    return (
        article.query_selector("button:has-text('Show more')") is not None
        or article.query_selector("a:has-text('Show more')") is not None
    )


def _get_video_info(article: ElementHandle) -> Tuple[bool, Optional[str]]:
    text = article.inner_text()
    has_video = ("Embedded video" in text) or ("Play Video" in text)
    duration = None
    if has_video:
        m = re.search(r"\b(\d{1,2}:\d{2})\b", text)
        if m:
            duration = m.group(1)
    return has_video, duration


def _extract_counts_from_group(article: ElementHandle) -> Dict[str, Optional[int]]:
    counts: Dict[str, Optional[int]] = {
        "replies": None,
        "reposts": None,
        "likes": None,
        "bookmarks": None,
        "views": None,
    }
    group = article.query_selector("[role='group']")
    if group:
        label = group.get_attribute("aria-label")
        if label:
            m = _GROUP_COUNTS_RE.search(label)
            if m:
                counts["replies"] = int(m.group(1))
                counts["reposts"] = int(m.group(2))
                counts["likes"] = int(m.group(3))
                counts["bookmarks"] = int(m.group(4))
                counts["views"] = int(m.group(5))
                return counts

    # Fallback: parse individual buttons/links
    for el in article.query_selector_all("button, a"):
        name = el.get_attribute("aria-label") or el.inner_text()
        if not name:
            continue
        lower = name.lower()
        if "replies" in lower or "reply" in lower:
            counts["replies"] = counts["replies"] or _parse_compact_number(name)
        elif "reposts" in lower or "repost" in lower:
            counts["reposts"] = counts["reposts"] or _parse_compact_number(name)
        elif "likes" in lower or "like" in lower:
            counts["likes"] = counts["likes"] or _parse_compact_number(name)
        elif "views" in lower:
            counts["views"] = counts["views"] or _parse_compact_number(name)

    return counts


def _extract_images(article: ElementHandle) -> List[str]:
    images: List[str] = []
    for img in article.query_selector_all("img"):
        src = img.get_attribute("src")
        alt = img.get_attribute("alt") or ""
        if not src:
            continue

        alt_lower = alt.lower()
        if alt_lower in ("profile picture", "square profile picture", ""):
            try:
                box = img.bounding_box()
                if box and box.get("width", 0) < 60 and box.get("height", 0) < 60:
                    continue
            except Exception:
                pass
            if alt_lower in ("profile picture", "square profile picture"):
                continue

        if "twimg.com/emoji" in src:
            continue
        if "Verified" in alt:
            continue

        if alt == "Image" or "media" in src:
            images.append(src)
        else:
            try:
                box = img.bounding_box()
                if box and box.get("width", 0) > 100 and box.get("height", 0) > 100:
                    images.append(src)
            except Exception:
                pass

    seen: set[str] = set()
    out: List[str] = []
    for u in images:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _extract_quote_tweet(article: ElementHandle) -> Optional[Dict[str, Any]]:
    text = article.inner_text()
    if "Quote" not in text:
        return None
    for link in article.query_selector_all("a[href*='/status/']"):
        link_text = link.inner_text()
        if len(link_text) > 50 and "@" in link_text:
            href = link.get_attribute("href")
            if href and "/status/" in href:
                m = re.search(r"/([^/]+)/status/", href)
                author = m.group(1) if m else None
                time_el = link.query_selector("time")
                time_str = time_el.get_attribute("datetime") if time_el else None
                return {
                    "author": author,
                    "link": f"https://x.com{href}" if href.startswith("/") else href,
                    "text": link_text[:500],
                    "time": time_str,
                }
    return None


def _extract_tweet(article: ElementHandle, target_username: str) -> Optional[Dict[str, Any]]:
    if _is_ad_tweet(article):
        return None

    is_repost, reposted_by = _get_repost_info(article)

    status_links = article.query_selector_all("a[href*='/status/']")
    href: Optional[str] = None
    tweet_id: Optional[str] = None
    original_author: Optional[str] = None

    for link in status_links:
        link_href = link.get_attribute("href")
        if link_href and "/status/" in link_href:
            if "analytics" in link_href:
                continue
            m = re.search(r"/([^/]+)/status/(\d+)", link_href)
            if m:
                author = m.group(1)
                tid = m.group(2)
                tweet_id = tid
                if is_repost or author != target_username:
                    original_author = author
            href = link_href
            break

    if not href:
        return None
    if href.startswith("/"):
        href = "https://x.com" + href

    time_el = article.query_selector("time")
    time_str = time_el.get_attribute("datetime") if time_el else None

    text = ""
    text_el = article.query_selector("div[data-testid='tweetText']")
    if text_el:
        text = text_el.inner_text()
    else:
        for div in article.query_selector_all("div[lang]"):
            t = div.inner_text()
            if len(t) > len(text):
                text = t

    region, is_pinned = _get_region_and_pinned(article)
    counts = _extract_counts_from_group(article)
    images = _extract_images(article)
    has_video, video_duration = _get_video_info(article)
    quoted_tweet = _extract_quote_tweet(article)
    is_truncated = _check_text_truncated(article)
    mentions = _extract_mentions(text)
    urls = _extract_urls(text)

    return {
        "time": time_str or "",
        "text": text or "",
        "tweetId": tweet_id or "",
        "images": images,
        "replies": counts.get("replies"),
        "reposts": counts.get("reposts"),
        "likes": counts.get("likes"),
        "bookmarks": counts.get("bookmarks"),
        "views": counts.get("views"),
        "link": href,
        "source": "Pinned" if is_pinned else (region or "Profile timeline"),
        "isPinned": is_pinned,
        "isRepost": is_repost,
        "repostedBy": reposted_by,
        "originalAuthor": original_author or target_username,
        "isAd": False,
        "hasVideo": has_video,
        "videoDuration": video_duration,
        "quotedTweet": quoted_tweet,
        "mentions": mentions,
        "urls": urls,
        "isTextTruncated": is_truncated,
    }


def _scroll_to_load(page: Page, max_scrolls: int = 10) -> None:
    prev_count = 0
    for _ in range(max_scrolls):
        page.mouse.wheel(0, 1200)
        page.wait_for_timeout(350)
        articles = page.query_selector_all("article[data-testid='tweet']")
        c = len(articles)
        if c <= prev_count:
            page.keyboard.press("End")
            page.wait_for_timeout(350)
            articles2 = page.query_selector_all("article[data-testid='tweet']")
            c2 = len(articles2)
            if c2 <= prev_count:
                break
            prev_count = c2
        else:
            prev_count = c


def _is_login_wall(page: Page) -> bool:
    # URL-based detection
    if "/login" in page.url or "/i/flow/" in page.url:
        return True
    # Modal detection
    modal = page.query_selector("[role='dialog'][aria-modal='true']")
    if modal:
        modal_text = modal.inner_text().lower()
        if any(kw in modal_text for kw in ["sign in", "log in", "create account", "join", "continue"]):
            return True
    # Body text detection as fallback
    try:
        body_text = page.inner_text("body").lower()
        if any(kw in body_text for kw in ["log in", "sign in", "create account", "to view posts", "see more"]):
            return True
    except Exception:
        pass
    return False


def list_all_tweets(username: str, headless: bool = False, save: bool = True) -> List[Post]:
    """Open X user profile and collect all non-ad tweets.

    Flow:
    1. Build profile URL and connect over CDP (see _login_x).
    2. If login wall or not authenticated, call _login_x(), then retry.
    3. Scroll to load, extract tweets, filter ads, return list of dicts (string values).

    Returns a list of `Post` objects. Each post is also auto-saved into the
    database using neutral sentiment and empty tickers/summary by default.
    """
    load_dotenv()
    cdp_url = os.getenv("X_CDP_URL", "http://localhost:9222")
    profile_url = f"https://x.com/{username}"

    def _iso_to_unix(ts: Optional[str]) -> int:
        if not ts:
            return 0
        try:
            s = ts.strip()
            # Handle trailing 'Z' by converting to +00:00
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            dt = datetime.fromisoformat(s)
            return int(dt.timestamp())
        except Exception:
            return 0

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(cdp_url)
        if not browser.contexts:
            browser.close()
            raise RuntimeError("No browser contexts available via CDP. Ensure Chrome was launched with user-data-dir.")
        context = browser.contexts[0]
        context.set_default_timeout(30000)
        page = context.new_page()

        page.goto(profile_url, wait_until="domcontentloaded")
        logging.info("Navigated to profile: %s", profile_url)

        if _is_login_wall(page) or not _has_auth_cookies(context):
            logging.info("Login required; performing login flow")
            browser.close()
            # Perform login using the current Playwright instance to avoid nested contexts
            _login_x(p, cdp_url=cdp_url, headless=headless)
            # Reconnect and navigate again
            browser = p.chromium.connect_over_cdp(cdp_url)
            context = browser.contexts[0]
            context.set_default_timeout(30000)
            page = context.new_page()
            page.goto(profile_url, wait_until="domcontentloaded")
            logging.info("Post-login navigation complete: %s", profile_url)

        # Minimal waits (best effort): prefer direct collection
        try:
            page.wait_for_selector("article[data-testid='tweet']", timeout=3000)
        except Exception:
            try:
                page.wait_for_selector("div[lang]", timeout=2000)
            except Exception:
                pass

        def _collect_articles() -> List[ElementHandle]:
            # Try immediate collection first (no scroll)
            selectors = [
                "article[data-testid='tweet']",
                "div[data-testid='tweet']",
                "article",
            ]
            for sel in selectors:
                items = page.query_selector_all(sel)
                if items:
                    return items
            # If none, attempt limited scroll then re-collect
            _scroll_to_load(page, max_scrolls=8)
            for sel in selectors:
                items = page.query_selector_all(sel)
                if items:
                    return items
            return []

        articles = _collect_articles()
        logging.info("Found %d tweet articles initially", len(articles))

        # If none found, try switching to the Posts tab, then retry once
        if not articles:
            try:
                logging.info("No articles found; attempting to select 'Posts' tab")
                # Try common tab selectors
                tab = None
                try:
                    tab = page.get_by_role("link", name=re.compile("Posts", re.I))
                    if tab.count() > 0:
                        tab.first.click()
                        page.wait_for_timeout(800)
                except Exception:
                    pass
                if not tab or tab.count() == 0:
                    el = page.locator("[role='tab']:has-text('Posts')").first
                    if el.count() > 0:
                        el.click()
                        page.wait_for_timeout(800)
                # Retry collect
                articles = _collect_articles()
                logging.info("After selecting 'Posts', found %d articles", len(articles))
            except Exception:
                logging.debug("Selecting 'Posts' tab failed; proceeding without tab switch")

        # If still none, try alternate URLs for profile (live/latest or enforce English)
        if not articles:
            try:
                alt_urls = [
                    f"{profile_url}?f=live",
                    f"{profile_url}?lang=en",
                ]
                for u in alt_urls:
                    logging.info("Retrying with alternate URL: %s", u)
                    page.goto(u, wait_until="domcontentloaded")
                    try:
                        page.wait_for_selector("div[lang]", timeout=3000)
                    except Exception:
                        pass
                    articles = _collect_articles()
                    logging.info("Alt URL found %d articles", len(articles))
                    if articles:
                        break
            except Exception:
                logging.debug("Alternate URL navigation failed; proceeding")

        # If still none, try re-login once (cookies may be stale)
        if not articles:
            try:
                logging.info("Still no articles; retrying after login refresh")
                browser.close()
                _login_x(p, cdp_url=cdp_url, headless=headless)
                browser = p.chromium.connect_over_cdp(cdp_url)
                context = browser.contexts[0]
                context.set_default_timeout(30000)
                page = context.new_page()
                page.goto(profile_url, wait_until="domcontentloaded")
                try:
                    page.wait_for_selector("div[lang]", timeout=3000)
                except Exception:
                    pass
                articles = _collect_articles()
                logging.info("Post re-login, found %d articles", len(articles))
            except Exception:
                logging.debug("Re-login refresh failed; continuing")

        seen: set[str] = set()
        results: List[Post] = []

        for article in articles:
            item = _extract_tweet(article, username)
            if not item:
                continue
            key = item.get("tweetId") or item.get("link") or ""
            if not key or key in seen:
                continue
            seen.add(key)
            # Build Post model
            post = Post(
                source="x",
                source_id=item.get("tweetId", "") or key,
                source_url=item.get("link", ""),
                content=item.get("text", ""),
                author_id=(item.get("originalAuthor") or username) or username,
                author_name=(item.get("originalAuthor") or username) or username,
                post_time=_iso_to_unix(item.get("time")),
                likes=int(item.get("likes") or 0) if item.get("likes") is not None else 0,
                comments=int(item.get("replies") or 0) if item.get("replies") is not None else 0,
                shares=int(item.get("reposts") or 0) if item.get("reposts") is not None else 0,
                bookmarks=int(item.get("bookmarks") or 0) if item.get("bookmarks") is not None else 0,
                views=int(item.get("views") or 0) if item.get("views") is not None else 0,
                images=list(item.get("images") or []),
                video_url="",
                quoted_url=(item.get("quotedTweet", {}) or {}).get("link", ""),
                is_retweet=bool(item.get("isRepost") or False),
                is_reply=False,
                original_source_id="",
                region=str(item.get("source") or ""),
                is_pinned=bool(item.get("isPinned") or False),
                is_ad=bool(item.get("isAd") or False),
                mentions=list(item.get("mentions") or []),
                urls=list(item.get("urls") or []),
                video_duration=str(item.get("videoDuration") or ""),
                is_text_truncated=bool(item.get("isTextTruncated") or False),
            )

            # Optional persistence (default: enabled). When disabled, the caller
            # can decide how and when to save, e.g. after LLM verification.
            if save:
                try:
                    if not SentimentModel.exists_source_id("x", post.source_id):
                        # Mandatory LLM verification before persistence
                        result = llm_analyze(post)
                        if result.get("is_valid"):
                            post.save(
                                sentiment=str(result.get("sentiment", "neutral")),
                                tickers=list(result.get("tickers", []) or []),
                                summary=str(result.get("summary", "")),
                            )
                        # If not valid, skip saving silently
                except Exception:
                    # Keep scraping resilient; do not fail on DB errors
                    pass

            results.append(post)

        # Sort by post_time desc
        results.sort(key=lambda x: x.post_time, reverse=True)
        browser.close()
        return results


class XCollector(BaseCollector):
    """Collector wrapper for X/Twitter that enforces LLM verification before save.

    This class preserves the existing scraping behavior by reusing
    `list_all_tweets()` with `save=False`, then performs mandatory LLM
    verification and persists only validated posts with the LLM results.
    """

    source_name: str = "x"

    def llm_verify_post(self, text: str) -> dict:
        """Run lightweight LLM verification and classification on raw text.

        Returns a dict: {is_valid, sentiment, tickers, summary}.
        """
        # Build a minimal Post for analysis context
        p = Post(
            source=self.source_name,
            source_id="temp-0",
            source_url="https://x.com/",
            content=text or "",
            author_id="x",
            author_name="x",
            post_time=0,
            likes=0,
            comments=0,
            shares=0,
        )
        return llm_analyze(p)

    def fetch_by_symbol(self, symbol: str, limit: int = 50, since_ts: int = 0) -> List[dict]:
        """X does not natively fetch by symbol; return empty list for now.

        Future enhancement could filter fetched posts whose content mentions the
        given symbol.
        """
        return []

    def fetch_trending(self, limit: int = 50, since_ts: int = 0) -> List[dict]:
        """Fetch recent posts from enabled X usernames and save after LLM verify.

        - Uses `get_enabled_x_usernames()` to enumerate profiles
        - Scrapes posts via `list_all_tweets(username, save=False)`
        - Applies time window filter
        - Runs LLM verification; only persists validated posts with LLM results
        - Returns the list of validated Post objects (raw items for BaseCollector)
        """
        usernames: List[str]
        try:
            usernames = get_enabled_x_usernames()
        except Exception:
            usernames = []

        validated: List[Post] = []
        for uname in usernames[:]:
            try:
                posts = list_all_tweets(uname, headless=False, save=False)
            except Exception:
                posts = []

            # Time filter
            if since_ts:
                posts = [p for p in posts if int(getattr(p, "post_time", 0) or 0) >= since_ts]

            # Enforce LLM verification before save
            for p in posts[:limit]:
                try:
                    result = llm_analyze(p)
                except Exception:
                    result = {
                        "is_valid": False,
                        "sentiment": "neutral",
                        "tickers": [],
                        "summary": "",
                    }

                if not result.get("is_valid"):
                    # Skip persistence if verification fails
                    continue

                # Persist with LLM outputs if not already saved
                try:
                    if not SentimentModel.exists_source_id("x", p.source_id):
                        p.save(
                            sentiment=str(result.get("sentiment", "neutral")),
                            tickers=list(result.get("tickers", []) or []),
                            summary=str(result.get("summary", "")),
                        )
                except Exception:
                    # Persistence errors are non-fatal for collection
                    pass

                validated.append(p)

        return validated

    def _to_post(self, raw: dict) -> Post:
        """Convert raw item to Post. Accepts Post passthrough or dict mapping."""
        if isinstance(raw, Post):
            return raw
        # Minimal mapping for dict inputs (best-effort)
        return Post(
            source=str(raw.get("source", self.source_name)),
            source_id=str(raw.get("source_id", "")),
            source_url=str(raw.get("source_url", "")),
            content=str(raw.get("content", "")),
            author_id=str(raw.get("author_id", "")),
            author_name=str(raw.get("author_name", "")),
            post_time=int(raw.get("post_time", 0) or 0),
            likes=int(raw.get("likes", 0) or 0),
            comments=int(raw.get("comments", 0) or 0),
            shares=int(raw.get("shares", 0) or 0),
            bookmarks=int(raw.get("bookmarks", 0) or 0),
            views=int(raw.get("views", 0) or 0),
            images=list(raw.get("images", []) or []),
            video_url=str(raw.get("video_url", "")),
            quoted_url=str(raw.get("quoted_url", "")),
            is_retweet=bool(raw.get("is_retweet", False)),
            is_reply=bool(raw.get("is_reply", False)),
            original_source_id=str(raw.get("original_source_id", "")),
            region=str(raw.get("region", "")),
            is_pinned=bool(raw.get("is_pinned", False)),
            is_ad=bool(raw.get("is_ad", False)),
            mentions=list(raw.get("mentions", []) or []),
            urls=list(raw.get("urls", []) or []),
            video_duration=str(raw.get("video_duration", "")),
            is_text_truncated=bool(raw.get("is_text_truncated", False)),
        )
