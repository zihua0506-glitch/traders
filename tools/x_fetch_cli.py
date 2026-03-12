#!/usr/bin/env python3
"""Fetch recent tweets for users listed in x_user_id.json via RapidAPI."""

import json
import os
import sys

import importlib.util

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))

_api_path = os.path.join(PROJECT_ROOT, "collectors", "x-rapid-api.py")
_spec = importlib.util.spec_from_file_location("x_rapid_api", _api_path)
api = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(api)
USER_LIST_PATH = os.path.join(PROJECT_ROOT, "x_user_id.json")


def _format_tweet(t: dict) -> str:
    screen_name = t["author"]["screen_name"] or "unknown"
    created_at = t["created_at"] or ""
    text = (t["full_text"] or "").replace("\n", " ").strip()
    m = t["metrics"]

    line = f"[@{screen_name} {created_at}] {text}"
    line += f" | views={m['views']} likes={m['favorite_count']} rt={m['retweet_count']}"

    if t["is_retweet"] and t["retweet_of"]:
        rt = t["retweet_of"]
        rt_text = (rt["full_text"] or "").replace("\n", " ").strip()
        line += f" [RETWEET of @{rt['author']['screen_name']}]: {rt_text}"

    if t["is_quote"] and t["quote_of"]:
        qt = t["quote_of"]
        qt_text = (qt["full_text"] or "").replace("\n", " ").strip()
        line += f" [QUOTE of @{qt['author']['screen_name']}]: {qt_text}"

    return line


def main() -> str:
    with open(USER_LIST_PATH, "r", encoding="utf-8") as f:
        users = json.load(f)

    lines = []
    for user in users:
        user_id = user["user_id"]
        label = user.get("label", user_id)
        print(f"Fetching tweets for {label} ({user_id})...", file=sys.stderr)

        try:
            tweets = api.fetch_tweets(user_id, count=20, recent_hours=24, max_count=20)
        except Exception as e:
            print(f"Error fetching {label}: {e}", file=sys.stderr)
            continue

        for t in tweets:
            lines.append(_format_tweet(t))

    result = "\n".join(lines)
    print(result)
    return result


if __name__ == "__main__":
    main()
