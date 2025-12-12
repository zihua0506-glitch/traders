#!/usr/bin/env python3
import os
import sys
from dotenv import load_dotenv

# Ensure repo root is on sys.path for package imports when running as a script
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from collectors.base import BaseCollector
from collectors.x import loginX


PORT = 9222


def main():
    load_dotenv()
    profile_dir = os.getenv("play_wright_profile_path")
    if not profile_dir:
        print("Environment variable 'play_wright_profile_path' is required")
        sys.exit(1)

    try:
        BaseCollector.launch_local_chrome_cdp()
    except Exception as e:
        print(f"Failed to launch Chrome with CDP: {e}")
        sys.exit(1)

    os.environ["X_CDP_URL"] = f"http://localhost:{PORT}"

    try:
        loginX(headless=False)
        print("Login completed successfully")
    except Exception as e:
        print(f"Login failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
