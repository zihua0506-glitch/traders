from typing import Optional, List, Dict, Any, Tuple
import re
import subprocess
import time
import urllib.request
import json
from datetime import datetime

import os
from dotenv import load_dotenv
from playwright.sync_api import (
    sync_playwright,
    TimeoutError as PlaywrightTimeoutError,
    Page,
    ElementHandle,
)

from models import Post
from db import SentimentModel


def loginX(headless: bool = False) -> None:
    """Login to X (Twitter) by connecting to a running Chrome via CDP.

    Expects you to start Chrome manually with remote debugging and the desired
    profile directory, e.g.:
    `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome \
      --remote-debugging-port=9222 \
      --user-data-dir="/Users/jolu/.playwright-mcp/profile"`

    Reads env via dotenv:
      - `play_wright_profile_path`
      - `X_USERNAME`, `X_PASSWORD`
      - `X_CDP_URL` (optional, default `http://localhost:9222`)
    """

    load_dotenv()
    profile_dir = os.getenv("play_wright_profile_path")
    username = os.getenv("X_USERNAME")
    password = os.getenv("X_PASSWORD")
    email = os.getenv("X_EMAIL")
    cdp_url = os.getenv("X_CDP_URL", "http://localhost:9222")

    if not profile_dir:
        raise RuntimeError("Environment variable 'play_wright_profile_path' is required")
    if not username or not password:
        raise RuntimeError("Environment variables 'X_USERNAME' and 'X_PASSWORD' are required")

    with sync_playwright() as p:
        # Connect to already-running Chrome via CDP
        try:
            browser = p.chromium.connect_over_cdp(cdp_url)
        except Exception as e:
            raise RuntimeError(f"Failed to connect over CDP at {cdp_url}: {e}")

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
COMPACT_NUM_RE = re.compile(r"^([0-9]+(?:\.[0-9]+)?)([KMB])?$", re.IGNORECASE)
MENTION_RE = re.compile(r"@[\w]+")
URL_RE = re.compile(r"https?://[^\s]+")
GROUP_COUNTS_RE = re.compile(
    r"(\d+)\s*replies.*?(\d+)\s*reposts.*?(\d+)\s*likes.*?(\d+)\s*bookmarks.*?(\d+)\s*views",
    re.IGNORECASE,
)

MULTIPLIERS = {
    "K": 1_000,
    "M": 1_000_000,
    "B": 1_000_000_000,
}


def parse_compact_number(s: Optional[str]) -> Optional[int]:
    """Parse numbers like '1.1K', '6.1M', '123' into int or None."""
    if not s:
        return None
    s = s.strip().replace(",", "")
    m = COMPACT_NUM_RE.match(s)
    if not m:
        parts = s.split()
        if parts:
            return parse_compact_number(parts[0])
        return None
    num, suffix = m.groups()
    value = float(num)
    if suffix:
        value *= MULTIPLIERS.get(suffix.upper(), 1)
    return int(value)


def extract_mentions(text: str) -> List[str]:
    return MENTION_RE.findall(text) if text else []


def extract_urls(text: str) -> List[str]:
    return URL_RE.findall(text) if text else []


def is_ad_tweet(article: ElementHandle) -> bool:
    text = article.inner_text()
    lines = text.split("\n")
    for line in lines[:10]:
        if line.strip() == "Ad":
            return True
    return False


def get_repost_info(article: ElementHandle) -> Tuple[bool, Optional[str]]:
    text = article.inner_text()
    m = re.match(r"^(.+?)\s+reposted", text, re.IGNORECASE)
    if m:
        return True, m.group(1).strip()
    return False, None


def get_region_and_pinned(article: ElementHandle) -> Tuple[str, bool]:
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


def check_text_truncated(article: ElementHandle) -> bool:
    return (
        article.query_selector("button:has-text('Show more')") is not None
        or article.query_selector("a:has-text('Show more')") is not None
    )


def get_video_info(article: ElementHandle) -> Tuple[bool, Optional[str]]:
    text = article.inner_text()
    has_video = ("Embedded video" in text) or ("Play Video" in text)
    duration = None
    if has_video:
        m = re.search(r"\b(\d{1,2}:\d{2})\b", text)
        if m:
            duration = m.group(1)
    return has_video, duration


def extract_counts_from_group(article: ElementHandle) -> Dict[str, Optional[int]]:
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
            m = GROUP_COUNTS_RE.search(label)
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
            counts["replies"] = counts["replies"] or parse_compact_number(name)
        elif "reposts" in lower or "repost" in lower:
            counts["reposts"] = counts["reposts"] or parse_compact_number(name)
        elif "likes" in lower or "like" in lower:
            counts["likes"] = counts["likes"] or parse_compact_number(name)
        elif "views" in lower:
            counts["views"] = counts["views"] or parse_compact_number(name)

    return counts


def extract_images(article: ElementHandle) -> List[str]:
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


def extract_quote_tweet(article: ElementHandle) -> Optional[Dict[str, Any]]:
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


def extract_tweet(article: ElementHandle, target_username: str) -> Optional[Dict[str, Any]]:
    if is_ad_tweet(article):
        return None

    is_repost, reposted_by = get_repost_info(article)

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

    region, is_pinned = get_region_and_pinned(article)
    counts = extract_counts_from_group(article)
    images = extract_images(article)
    has_video, video_duration = get_video_info(article)
    quoted_tweet = extract_quote_tweet(article)
    is_truncated = check_text_truncated(article)
    mentions = extract_mentions(text)
    urls = extract_urls(text)

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


def scroll_to_load(page: Page, max_scrolls: int = 30) -> None:
    prev_count = 0
    for _ in range(max_scrolls):
        page.mouse.wheel(0, 2000)
        page.wait_for_timeout(800)
        articles = page.query_selector_all("article[data-testid='tweet']")
        c = len(articles)
        if c <= prev_count:
            page.keyboard.press("End")
            page.wait_for_timeout(800)
            articles2 = page.query_selector_all("article[data-testid='tweet']")
            c2 = len(articles2)
            if c2 <= prev_count:
                break
            prev_count = c2
        else:
            prev_count = c


def _is_login_wall(page: Page) -> bool:
    if "/login" in page.url or "/i/flow/" in page.url:
        return True
    modal = page.query_selector("[role='dialog'][aria-modal='true']")
    if modal:
        modal_text = modal.inner_text().lower()
        if any(kw in modal_text for kw in ["sign in", "log in", "create account"]):
            return True
    return False


def list_all_tweets(username: str, headless: bool = False) -> List[Post]:
    """Open X user profile and collect all non-ad tweets.

    Flow:
    1. Build profile URL and connect over CDP (see loginX).
    2. If login wall or not authenticated, call loginX(), then retry.
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

        if _is_login_wall(page) or not _has_auth_cookies(context):
            browser.close()
            # Perform login via existing CDP session
            loginX(headless=headless)
            # Reconnect and navigate again
            browser = p.chromium.connect_over_cdp(cdp_url)
            context = browser.contexts[0]
            context.set_default_timeout(30000)
            page = context.new_page()
            page.goto(profile_url, wait_until="domcontentloaded")

        # Wait for tweets to be visible (best effort)
        try:
            page.wait_for_selector("article[data-testid='tweet']", timeout=15000)
        except Exception:
            pass

        scroll_to_load(page)
        articles = page.query_selector_all("article[data-testid='tweet']")
        if not articles:
            articles = page.query_selector_all("article")

        seen: set[str] = set()
        results: List[Post] = []

        for article in articles:
            item = extract_tweet(article, username)
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

            # Auto-save with safe defaults; skip on unique conflicts
            try:
                # Use the model's own save method for simplicity
                if not SentimentModel.exists_source_id("x", post.source_id):
                    post.save()
            except Exception:
                # Keep scraping resilient; do not fail on DB errors
                pass

            results.append(post)

        # Sort by post_time desc
        results.sort(key=lambda x: x.post_time, reverse=True)
        browser.close()
        return results
