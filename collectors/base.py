"""Base collector module.

Defines the abstract base class for all data collectors.
"""

from __future__ import annotations

import logging
import os
import subprocess
import urllib.request
import socket
import random
import time
from abc import ABC, abstractmethod
from typing import List, Tuple, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from models import Post


logger = logging.getLogger(__name__)

# Random user agents to avoid detection
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

# Default configuration
DEFAULT_TIMEOUT = 15
DEFAULT_DELAY = 0.5


class BaseCollector(ABC):
    """Abstract base class for all data collectors.

    Provides common functionality:
    - HTTP session management with retries
    - User-Agent rotation
    - Rate limiting
    - Time window filtering
    """

    # Subclasses must override this
    source_name: str = "base"

    def __init__(
        self,
        timeout: int = DEFAULT_TIMEOUT,
        delay: float = DEFAULT_DELAY,
        max_retries: int = 3,
    ):
        """Initialize the collector.

        Args:
            timeout: Request timeout in seconds
            delay: Delay between requests in seconds
            max_retries: Maximum number of retries for failed requests
        """
        self.timeout = timeout
        self.delay = delay
        self.session = self._create_session(max_retries)

    def _create_session(self, max_retries: int) -> requests.Session:
        """Create a requests session with retry configuration."""
        session = requests.Session()
        session.headers.update({
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "application/json, text/html, */*",
        })

        retries = Retry(
            total=max_retries,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        session.mount("https://", HTTPAdapter(max_retries=retries))
        session.mount("http://", HTTPAdapter(max_retries=retries))

        return session

    def _get(self, url: str, params: dict = None, **kwargs) -> requests.Response:
        """Make a GET request with configured timeout.

        Args:
            url: Request URL
            params: Query parameters
            **kwargs: Additional arguments passed to requests.get

        Returns:
            Response object

        Raises:
            requests.exceptions.RequestException: On request failure
        """
        kwargs.setdefault("timeout", self.timeout)
        return self.session.get(url, params=params, **kwargs)

    def _rate_limit(self, delay: float = None):
        """Sleep for rate limiting.

        Args:
            delay: Override delay (uses instance delay if None)
        """
        sleep_time = delay if delay is not None else self.delay
        if sleep_time > 0:
            time.sleep(sleep_time)

    def _filter_by_time(
        self,
        posts: List[dict],
        since_ts: int,
        time_field: str = "post_time",
    ) -> List[dict]:
        """Filter posts by timestamp.

        Args:
            posts: List of post dictionaries
            since_ts: Unix timestamp threshold
            time_field: Key name for the timestamp field

        Returns:
            Filtered list of posts
        """
        if not since_ts:
            return posts
        return [p for p in posts if p.get(time_field, 0) >= since_ts]

    @abstractmethod
    def fetch_by_symbol(
        self,
        symbol: str,
        limit: int = 50,
        since_ts: int = 0,
    ) -> List[dict]:
        """Fetch posts/news for a specific stock symbol.

        Args:
            symbol: Stock ticker symbol (e.g., "AAPL")
            limit: Maximum number of items to fetch
            since_ts: Only return items after this timestamp

        Returns:
            List of raw data dictionaries
        """
        pass

    @abstractmethod
    def fetch_trending(
        self,
        limit: int = 50,
        since_ts: int = 0,
    ) -> List[dict]:
        """Fetch trending/latest posts.

        Args:
            limit: Maximum number of items to fetch
            since_ts: Only return items after this timestamp

        Returns:
            List of raw data dictionaries
        """
        pass

    @abstractmethod
    def _to_post(self, raw: dict) -> Post:
        """Convert raw data to Post model.

        Args:
            raw: Raw data dictionary from the source

        Returns:
            Normalized Post instance
        """
        pass

    def fetch_posts(
        self,
        hours: int,
        symbols: Optional[List[str]] = None,
        limit: int = 100,
    ) -> Tuple[List[Post], int]:
        """Unified interface to fetch posts.

        Args:
            hours: Time window in hours
            symbols: List of stock symbols (None for trending)
            limit: Maximum posts per symbol/source

        Returns:
            Tuple of (posts, total_count)
        """
        if hours <= 0:
            raise ValueError("hours must be a positive integer")

        now_ts = int(time.time())
        since_ts = now_ts - hours * 3600

        all_raw = []

        if symbols:
            for symbol in symbols:
                try:
                    raw = self.fetch_by_symbol(symbol, limit=limit, since_ts=since_ts)
                    all_raw.extend(raw)
                    logger.info(
                        "[%s] Fetched %d items for %s",
                        self.source_name, len(raw), symbol
                    )
                except Exception as e:
                    logger.error(
                        "[%s] Failed to fetch %s: %s",
                        self.source_name, symbol, e
                    )
                self._rate_limit()
        else:
            try:
                raw = self.fetch_trending(limit=limit, since_ts=since_ts)
                all_raw.extend(raw)
                logger.info(
                    "[%s] Fetched %d trending items",
                    self.source_name, len(raw)
                )
            except Exception as e:
                logger.error(
                    "[%s] Failed to fetch trending: %s",
                    self.source_name, e
                )

        posts = []
        for raw in all_raw:
            try:
                post = self._to_post(raw)
                posts.append(post)
            except Exception as e:
                logger.warning(
                    "[%s] Failed to convert post: %s",
                    self.source_name, e
                )

        return posts, len(posts)

    @staticmethod
    def launch_local_chrome_cdp() -> None:
        """Launch local Chrome with CDP enabled using env configuration.

        Reads environment variables:
        - `play_wright_profile_path`: Chrome user data dir
        - `CHROME_PATH` (optional): explicit Chrome binary path

        Uses a fixed CDP port 9222 and waits for `http://localhost:9222/json/version`.
        On macOS, if `CHROME_PATH` is not set, uses `open -a "Google Chrome" --args ...`.

        Raises RuntimeError if CDP endpoint does not become ready within timeout.
        """
        profile_dir = os.getenv("play_wright_profile_path")
        if not profile_dir:
            raise RuntimeError("Environment variable 'play_wright_profile_path' is required")

        chrome_path = os.getenv("CHROME_PATH") or "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        port = 9222
        args = [
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile_dir}",
        ]

        # If port is already open, assume browser is running and skip launching
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=2):
                return
        except Exception:
            pass
        endpoint = f"http://localhost:{port}/json/version"

        # Prefer explicit binary path; if it fails, try macOS 'open -a'
        cmd = [chrome_path] + args
        try:
            subprocess.Popen(cmd)
        except Exception:
            cmd = ["open", "-a", "Google Chrome", "--args"] + args
            res = subprocess.run(cmd, capture_output=True)
            if res.returncode != 0:
                stderr = res.stderr.decode(errors="ignore") if res.stderr else ""
                raise RuntimeError(f"Failed to launch Chrome: {stderr.strip() or 'open -a failed'}")

        # Wait for CDP to be ready
        deadline = time.time() + 20
        last_err = None
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(endpoint, timeout=2) as resp:
                    if resp.status == 200:
                        return
            except Exception as e:
                last_err = e
            time.sleep(0.5)

        raise RuntimeError(f"CDP endpoint not ready at {endpoint}: {last_err}")
