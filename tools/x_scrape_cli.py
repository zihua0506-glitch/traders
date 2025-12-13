#!/usr/bin/env python3
import os
import sys
import json
import argparse
import platform
import subprocess
import socket
import time
import random
import logging
import urllib.request
from typing import List, Optional, Tuple, Dict
from dotenv import load_dotenv

# Ensure repo root is on sys.path for package imports when running as a script
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from collectors.x import list_all_tweets
from models import Post
from models.x_username import get_enabled_x_usernames


PORT = 9222


def main():
    parser = argparse.ArgumentParser(
        description="Scrape tweets from X user profiles via Playwright/CDP"
    )
    parser.add_argument(
        "--username",
        default=None,
        help="X username to scrape; if omitted, scrape all enabled usernames from DB",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run login flow in headless mode (default: false)",
    )
    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logging.info("Starting X scrape CLI")

    load_dotenv()
    profile_dir = os.getenv("play_wright_profile_path")
    if not profile_dir:
        logging.error("Environment variable 'play_wright_profile_path' is required")
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

    def find_chrome_pid(profile: str, port: int) -> Optional[int]:
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

    def find_remote_debug_pid(port: int) -> Optional[int]:
        """Find a process PID that was launched with --remote-debugging-port=PORT.

        Falls back to lsof to find a listener on the given port.
        """
        try:
            # Scan process args for the flag
            if platform.system() == "Darwin":
                cmd = ["ps", "ax", "-o", "pid=,command="]
            else:
                cmd = ["ps", "-eo", "pid=,args="]
            out = subprocess.check_output(cmd).decode(errors="ignore")
            for line in out.splitlines():
                if f"--remote-debugging-port={port}" in line:
                    pid_str = line.strip().split()[0]
                    try:
                        return int(pid_str)
                    except Exception:
                        continue
        except Exception:
            pass
        # Fallback: lsof on the port
        try:
            lsof_cmd = ["lsof", "-n", f"-iTCP:{port}", "-sTCP:LISTEN", "-P"]
            out = subprocess.check_output(lsof_cmd, stderr=subprocess.DEVNULL).decode(errors="ignore")
            for line in out.splitlines()[1:]:  # skip header
                parts = line.split()
                if parts:
                    try:
                        # PID is typically in the 2nd column
                        pid = int(parts[1])
                        return pid
                    except Exception:
                        continue
        except Exception:
            pass
        return None

    def list_remote_debug_pids(port: int) -> List[int]:
        """List all process PIDs associated with the given remote debugging port.

        Combines processes launched with the flag and processes actively listening
        on the port via lsof. Deduplicates results.
        """
        pids: List[int] = []
        # Collect by flag
        try:
            if platform.system() == "Darwin":
                cmd = ["ps", "ax", "-o", "pid=,command="]
            else:
                cmd = ["ps", "-eo", "pid=,args="]
            out = subprocess.check_output(cmd).decode(errors="ignore")
            for line in out.splitlines():
                if f"--remote-debugging-port={port}" in line:
                    try:
                        pids.append(int(line.strip().split()[0]))
                    except Exception:
                        continue
        except Exception:
            pass
        # Collect by lsof
        try:
            lsof_cmd = ["lsof", "-n", f"-iTCP:{port}", "-sTCP:LISTEN", "-P"]
            out = subprocess.check_output(lsof_cmd, stderr=subprocess.DEVNULL).decode(errors="ignore")
            for line in out.splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        pids.append(int(parts[1]))
                    except Exception:
                        continue
        except Exception:
            pass
        # Dedup while preserving order
        seen = set()
        uniq: List[int] = []
        for pid in pids:
            if pid not in seen:
                seen.add(pid)
                uniq.append(pid)
        return uniq

    def launch_chrome_cdp(profile: str, port: int = PORT, headless: bool = False) -> Tuple[Optional[subprocess.Popen], Optional[int]]:
        if port_open(port):
            # Port already in use; capture PID so we can kill on exit
            existing_pid = find_remote_debug_pid(port)
            logging.info("Remote debugging port %s already open (pid=%s)", port, existing_pid)
            return None, existing_pid
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
        proc: Optional[subprocess.Popen] = None
        try:
            proc = subprocess.Popen([chrome_path] + args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
        pid = proc.pid if proc else (find_chrome_pid(profile, port) or find_remote_debug_pid(port))
        return proc, pid

    # Launch Chrome with CDP (self-managed) and set X_CDP_URL
    logging.info("Launching Chrome with CDP on port %s", PORT)
    try:
        proc, pid = launch_chrome_cdp(profile_dir, PORT, headless=args.headless)
    except Exception as e:
        logging.exception("Failed to launch Chrome with CDP: %s", e)
        sys.exit(1)

    os.environ["X_CDP_URL"] = f"http://localhost:{PORT}"

    # Scrape tweets
    usernames: List[str]
    if args.username:
        usernames = [args.username]
        logging.info("Scraping single username: %s", args.username)
    else:
        logging.info("No username provided; fetching enabled usernames from DB")
        try:
            usernames = get_enabled_x_usernames()
        except Exception as e:
            logging.exception("Failed to fetch usernames from DB: %s", e)
            sys.exit(1)
        if not usernames:
            logging.warning("No enabled usernames found in DB; exiting")
            # Close Chrome before exit
            try:
                if proc is not None:
                    proc.terminate()
            except Exception:
                pass
            sys.exit(0)

    posts_by_username: Dict[str, List[Post]] = {}
    for i, uname in enumerate(usernames, start=1):
        logging.info("[%d/%d] Begin scraping: %s", i, len(usernames), uname)
        try:
            posts_by_username[uname] = list_all_tweets(uname, headless=args.headless)
            logging.info(
                "[%d/%d] Scraped %d posts for %s",
                i,
                len(usernames),
                len(posts_by_username[uname]),
                uname,
            )
        except Exception as e:
            logging.exception("[%d/%d] Scrape failed for %s: %s", i, len(usernames), uname, e)
            posts_by_username[uname] = []

        if i < len(usernames):
            delay = random.randint(1, 5)
            logging.info("Sleeping %ds before next username", delay)
            time.sleep(delay)

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

    if args.username:
        # Backward-compatible single-username output
        posts = posts_by_username.get(args.username, [])
        output = {
            "username": args.username,
            "count": len(posts),
            "posts": [to_dict(p) for p in posts],
        }
    else:
        # Multi-username aggregated output
        output = {
            "usernames": usernames,
            "total_count": sum(len(v) for v in posts_by_username.values()),
            "by_username": {u: [to_dict(p) for p in posts_by_username.get(u, [])] for u in usernames},
        }
    logging.info("Scrape complete; printing JSON summary")
    print(json.dumps(output, ensure_ascii=False, indent=2))

    # Close only the Chrome instance we launched
    try:
        logging.info("Shutting down Chrome process")
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                logging.warning("Terminate timeout; killing Chrome process")
                proc.kill()
        # Kill by known pid (if any)
        if pid is not None:
            for sig in (15, 9):
                try:
                    os.kill(pid, sig)
                    if sig == 15:
                        time.sleep(1)
                except Exception:
                    pass
        # Kill all processes associated with the remote debugging port
        all_pids = list_remote_debug_pids(PORT)
        if all_pids:
            logging.info("Killing all processes on remote debugging port %s: %s", PORT, all_pids)
            for p in all_pids:
                for sig in (15, 9):
                    try:
                        os.kill(p, sig)
                        if sig == 15:
                            time.sleep(1)
                    except Exception:
                        pass
        else:
            logging.info("No remaining processes detected on port %s", PORT)
    except Exception:
        logging.exception("Error while shutting down Chrome")


if __name__ == "__main__":
    main()
