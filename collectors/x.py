from typing import Optional
import re
import subprocess
import time
import urllib.request

import os
from dotenv import load_dotenv
from playwright.sync_api import (
    sync_playwright,
    TimeoutError as PlaywrightTimeoutError,
)


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
