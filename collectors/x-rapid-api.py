import os
import sys
from datetime import datetime, timezone, timedelta

import truststore
truststore.inject_into_ssl()

import requests
from dotenv import load_dotenv

load_dotenv()

x_rapidapi_host=os.getenv("x-rapidapi-host")
BASE_URL = "https://"+x_rapidapi_host

HEADERS = {
    "x-rapidapi-key": os.getenv("x-rapidapi-key"),
    "x-rapidapi-host": x_rapidapi_host,
}


def get_user_id(username: str) -> str:
    resp = requests.get(f"{BASE_URL}/user", headers=HEADERS, params={"username": username}, timeout=15)
    resp.raise_for_status()
    return resp.json().get("result", {}).get("rest_id", "")


def get_user_tweets(user_id: str, count: int = 20) -> dict:
    resp = requests.get(
        f"{BASE_URL}/user-tweets",
        headers=HEADERS,
        params={"user": user_id, "count": str(count)},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()

def _extract_tweet(result: dict) -> dict | None:
    """Extract key fields from a single tweet result."""
    if not result or result.get("__typename") == "TweetTombstone":
        return None

    legacy = result.get("legacy", {})
    user_result = result.get("core", {}).get("user_results", {}).get("result", {})
    user_core = user_result.get("core", {})
    user_legacy = user_result.get("legacy", {})

    # Expand note_tweet full text if available
    note = result.get("note_tweet", {}).get("note_tweet_results", {}).get("result", {})
    full_text = note.get("text") or legacy.get("full_text", "")

    # Handle retweet: extract original tweet content
    rt_result = legacy.get("retweeted_status_result", {}).get("result", {})
    retweet_of = None
    if rt_result:
        rt_legacy = rt_result.get("legacy", {})
        rt_note = rt_result.get("note_tweet", {}).get("note_tweet_results", {}).get("result", {})
        rt_user = rt_result.get("core", {}).get("user_results", {}).get("result", {}).get("core", {})
        retweet_of = {
            "id": rt_legacy.get("id_str"),
            "full_text": rt_note.get("text") or rt_legacy.get("full_text", ""),
            "author": {
                "name": rt_user.get("name"),
                "screen_name": rt_user.get("screen_name"),
            },
        }

    # Handle quote tweet: extract quoted tweet content
    qt_result = result.get("quoted_status_result", {}).get("result", {})
    quote_of = None
    if qt_result and qt_result.get("__typename") != "TweetTombstone":
        qt_legacy = qt_result.get("legacy", {})
        qt_note = qt_result.get("note_tweet", {}).get("note_tweet_results", {}).get("result", {})
        qt_user = qt_result.get("core", {}).get("user_results", {}).get("result", {}).get("core", {})
        quote_of = {
            "id": qt_legacy.get("id_str"),
            "full_text": qt_note.get("text") or qt_legacy.get("full_text", ""),
            "author": {
                "name": qt_user.get("name"),
                "screen_name": qt_user.get("screen_name"),
            },
        }

    return {
        "id": legacy.get("id_str"),
        "created_at": legacy.get("created_at"),
        "full_text": full_text,
        "lang": legacy.get("lang"),
        "author": {
            "name": user_core.get("name"),
            "screen_name": user_core.get("screen_name"),
            "followers_count": user_legacy.get("followers_count"),
        },
        "metrics": {
            "favorite_count": legacy.get("favorite_count", 0),
            "retweet_count": legacy.get("retweet_count", 0),
            "reply_count": legacy.get("reply_count", 0),
            "quote_count": legacy.get("quote_count", 0),
            "bookmark_count": legacy.get("bookmark_count", 0),
            "views": int(result.get("views", {}).get("count", 0)),
        },
        "is_reply": bool(legacy.get("in_reply_to_status_id_str")),
        "is_retweet": retweet_of is not None,
        "is_quote": quote_of is not None,
        "retweet_of": retweet_of,
        "quote_of": quote_of,
        "conversation_id": legacy.get("conversation_id_str"),
    }


def filter_tweets(raw: dict) -> list[dict]:
    """Filter raw API response, return only meaningful tweets."""
    instructions = raw.get("result", {}).get("timeline", {}).get("instructions", [])
    tweets = []

    for instruction in instructions:
        # Handle TimelinePinEntry
        entry = instruction.get("entry")
        if entry:
            _process_entry(entry, tweets)

        # Handle TimelineAddEntries
        for entry in instruction.get("entries", []):
            _process_entry(entry, tweets)

    return tweets


def _process_entry(entry: dict, tweets: list):
    entry_id = entry.get("entryId", "")

    # Skip ads, who-to-follow, cursors
    if entry_id.startswith(("promoted-tweet-", "who-to-follow-", "cursor-")):
        return

    content = entry.get("content", {})
    typename = content.get("__typename")

    if typename == "TimelineTimelineItem":
        _process_item(content, tweets)
    elif typename == "TimelineTimelineModule":
        # Conversation threads
        for item_wrapper in content.get("items", []):
            item = item_wrapper.get("item", {})
            _process_item(item, tweets)


def _process_item(item: dict, tweets: list):
    item_content = item.get("itemContent", {})

    # Skip ads and non-tweet items
    if item_content.get("promotedMetadata") or item_content.get("__typename") != "TimelineTweet":
        return

    result = item_content.get("tweet_results", {}).get("result", {})

    # Handle TweetWithVisibilityResults wrapper
    if result.get("__typename") == "TweetWithVisibilityResults":
        result = result.get("tweet", {})

    tweet = _extract_tweet(result)
    if tweet and tweet["id"]:
        tweets.append(tweet)


def fetch_tweets(user_id: str, count: int = 20, *, recent_hours: float | None = None, max_count: int | None = None) -> list[dict]:
    """Fetch and filter tweets for a user, return clean tweet list.

    Args:
        recent_hours: Only keep tweets created within the last N hours.
        max_count: Return at most N tweets.
    """
    raw = get_user_tweets(user_id, count)
    tweets = filter_tweets(raw)

    if recent_hours is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=recent_hours)
        tweets = [t for t in tweets if _parse_created_at(t["created_at"]) >= cutoff]

    if max_count is not None:
        tweets = tweets[:max_count]

    return tweets


def _parse_created_at(created_at: str) -> datetime:
    """Parse Twitter's created_at format like 'Wed Oct 10 20:19:24 +0000 2018'."""
    return datetime.strptime(created_at, "%a %b %d %H:%M:%S %z %Y")


if __name__ == "__main__":
    tweets = fetch_tweets("44196397", 2)
    for t in tweets:
        print(f"[{t['created_at']}] {t['full_text']}")
        print(f"  views={t['metrics']['views']}  likes={t['metrics']['favorite_count']}  "
              f"rt={t['metrics']['retweet_count']}  reply={t['is_reply']}  "
              f"retweet={t['is_retweet']}  quote={t['is_quote']}")
        if t["retweet_of"]:
            rt = t["retweet_of"]
            print(f"  >> RT @{rt['author']['screen_name']}: {rt['full_text']}")
        if t["quote_of"]:
            qt = t["quote_of"]
            print(f"  >> QT @{qt['author']['screen_name']}: {qt['full_text']}")
        print()