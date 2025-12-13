#!/usr/bin/env python3
import os
import sys
import json
import argparse
import platform
import subprocess
import socket
import time
import urllib.request
from dotenv import load_dotenv

# Ensure repo root is on sys.path for package imports when running as a script
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from collectors.x import list_all_tweets
from models import Post


PORT = 9222


def main():
    parser = argparse.ArgumentParser(
        description="Scrape tweets from an X user profile via Playwright/CDP"
    )
    parser.add_argument(
        "--username",
        default="elonmusk",
        help="X username to scrape (default: elonmusk)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run login flow in headless mode (default: false)",
    )
    args = parser.parse_args()

    load_dotenv()
    profile_dir = os.getenv("play_wright_profile_path")
    if not profile_dir:
        print("Environment variable 'play_wright_profile_path' is required")
        sys.exit(1)

    def port_open(port: int) -> bool:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except Exception:
            return False

    def wait_cdp_ready(port: int, timeout: float = 20.0) -> bool:
        endpoint = f"http://localhost:{port}/json/version"
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(endpoint, timeout=2) as resp:
                    if resp.status == 200:
                        return True
            except Exception:
                pass
            time.sleep(0.5)
        return False

    def find_chrome_pid(profile: str, port: int) -> int | None:
        try:
            # macOS / Linux process scan
            if platform.system() == "Darwin":
                cmd = ["ps", "ax", "-o", "pid=,command="]
            else:
                cmd = ["ps", "-eo", "pid=,args="]
            out = subprocess.check_output(cmd).decode(errors="ignore")
            for line in out.splitlines():
                if f"--user-data-dir={profile}" in line and f"--remote-debugging-port={port}" in line:
                    pid_str = line.strip().split()[0]
                    try:
                        return int(pid_str)
                    except Exception:
                        continue
        except Exception:
            pass
        return None

    def launch_chrome_cdp(profile: str, port: int = PORT, headless: bool = False) -> tuple[subprocess.Popen | None, int | None]:
        if port_open(port):
            return None, None
        chrome_path = os.getenv("CHROME_PATH") or (
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
            if platform.system() == "Darwin" else "google-chrome"
        )
        args = [
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile}",
        ]
        if headless:
            # Use headless mode for Chrome; 'new' is recommended in modern versions
            args.append("--headless=new")
        proc: subprocess.Popen | None = None
        try:
            proc = subprocess.Popen([chrome_path] + args)
        except Exception:
            # macOS fallback: open -a (PID tracking via ps scan)
            if platform.system() == "Darwin":
                res = subprocess.run(["open", "-a", "Google Chrome", "--args"] + args, capture_output=True)
                if res.returncode != 0:
                    stderr = res.stderr.decode(errors="ignore") if res.stderr else ""
                    raise RuntimeError(f"Failed to launch Chrome: {stderr.strip() or 'open -a failed'}")
            else:
                raise
        if not wait_cdp_ready(port):
            raise RuntimeError("CDP endpoint not ready")
        pid = proc.pid if proc else find_chrome_pid(profile, port)
        return proc, pid

    # Launch Chrome with CDP (self-managed) and set X_CDP_URL
    try:
        proc, pid = launch_chrome_cdp(profile_dir, PORT, headless=args.headless)
    except Exception as e:
        print(f"Failed to launch Chrome with CDP: {e}")
        sys.exit(1)

    os.environ["X_CDP_URL"] = f"http://localhost:{PORT}"

    # Scrape tweets
    try:
        posts: list[Post] = list_all_tweets(args.username, headless=args.headless)
    except Exception as e:
        print(f"Scrape failed: {e}")
        sys.exit(1)

    def to_dict(p: Post) -> dict:
        return {
            "source": p.source,
            "source_id": p.source_id,
            "source_url": p.source_url,
            "content": p.content,
            "author_id": p.author_id,
            "author_name": p.author_name,
            "post_time": p.post_time,
            "likes": p.likes,
            "comments": p.comments,
            "shares": p.shares,
            "bookmarks": p.bookmarks,
            "views": p.views,
            "images": p.images,
            "video_url": p.video_url,
            "quoted_url": p.quoted_url,
            "is_retweet": p.is_retweet,
            "is_reply": p.is_reply,
            "original_source_id": p.original_source_id,
            "region": p.region,
            "is_pinned": p.is_pinned,
            "is_ad": p.is_ad,
            "mentions": p.mentions,
            "urls": p.urls,
            "video_duration": p.video_duration,
            "is_text_truncated": p.is_text_truncated,
        }

    output = {
        "username": args.username,
        "count": len(posts),
        "posts": [to_dict(p) for p in posts],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))

    # Close only the Chrome instance we launched
    try:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
        elif pid is not None:
            # Graceful, then force
            try:
                os.kill(pid, 15)
                time.sleep(1)
            except Exception:
                pass
            try:
                os.kill(pid, 9)
            except Exception:
                pass
    except Exception:
        pass


if __name__ == "__main__":
    main()
