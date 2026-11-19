"""Market window phase 3: headlines and X posts, read-only, cached, capped.

Scripted HTTP; the network is blocked."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from core.market.feeds import (NEWS_URL, REDDIT_URL, X_DAILY_POST_CAP, X_SEARCH_URL, FeedError, MarketFeeds,
                               feed_lines, fetch_headlines, fetch_reddit, fetch_x_posts, validate_subreddits)
from core.runtime.owner_settings import OwnerSettings, SettingsError

NOW = datetime(2026, 11, 19, 15, 0, tzinfo=timezone.utc)
KEYS = {"massive": "massivekey1", "x_bearer_token": "xbearer123456", "redditapis_token": "redditapistoken1"}


class Response:
    def __init__(self, status, data):
        self.status_code, self._data = status, data

    def json(self):
        return self._data


def news(n=6):
    return {"results": [{"title": f"Story {i} https://t.co/x", "publisher": {"name": "Wire"},
                         "published_utc": "2026-11-19T14:00:00Z"} for i in range(n)]}


def reddit(subreddit):
    return {"posts": [{"title": f"{subreddit} pinned", "subreddit": subreddit, "upvotes": 9999, "comments": 1,
                       "stickied": True},
                      {"title": f"{subreddit} thread", "subreddit": subreddit, "upvotes": len(subreddit) * 100,
                       "comments": 40, "stickied": False, "over_18": False}]}


def posts(n=10):
    return {"data": [{"text": f"$SPY post {i}", "public_metrics": {"like_count": i},
                      "created_at": "2026-11-19T14:30:00Z"} for i in range(n)]}


class Scripted:
    def __init__(self, status=200):
        self.status, self.calls = status, []

    def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if url not in (NEWS_URL, X_SEARCH_URL, REDDIT_URL):
            raise AssertionError("only the news, recent-search and Reddit listing addresses may be read: " + url)
        if self.status != 200:
            return Response(self.status, {"detail": "nope " + KEYS["x_bearer_token"]})
        if url == REDDIT_URL:
            return Response(200, reddit(kwargs["params"]["subreddit"]))
        return Response(200, news() if url == NEWS_URL else posts())


class Blocked(unittest.TestCase):
    def setUp(self):
        for target, name in ((socket.socket, "connect"), (socket, "create_connection")):
            blocked = patch.object(target, name, side_effect=AssertionError("network forbidden"))
            blocked.start()
            self.addCleanup(blocked.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)


class FetchTests(Blocked):
    def test_headlines_are_short_and_from_the_response(self):
        record = fetch_headlines("k" * 10, http_get=Scripted(), now=lambda: NOW)
        self.assertEqual(record["status"], "ok")
        self.assertEqual(len(record["items"]), 5)
        self.assertEqual(record["items"][0]["title"], "Story 0")  # Links removed.

    def test_law_firm_ads_and_self_promotion_are_filtered_out(self):
        class Noisy(Scripted):
            def __call__(self, url, **kwargs):
                self.calls.append((url, kwargs))
                if url == NEWS_URL:
                    return Response(200, {"results": [
                        {"title": "ROSEN, SKILLED INVESTOR COUNSEL, Encourages Triller Investors to Secure Counsel",
                         "publisher": {"name": "GlobeNewswire"}},
                        {"title": "Shareholder Alert: ClaimsFiler Reminds Investors With Losses", "publisher": {}},
                        {"title": "Fed holds rates steady", "publisher": {"name": "Wire"}}]})
                return Response(200, {"data": [
                    {"text": "$SPY read my substack post, subscribe", "public_metrics": {"like_count": 50}},
                    {"text": "$SPY breadth is thin today", "public_metrics": {"like_count": 12}},
                    {"text": "$QQQ moon", "public_metrics": {"like_count": 1}}]})
        heads = fetch_headlines("k" * 10, http_get=Noisy(), now=lambda: NOW)
        self.assertEqual([item["title"] for item in heads["items"]], ["Fed holds rates steady"])
        x = fetch_x_posts("t" * 10, ["SPY"], http_get=Noisy(), now=lambda: NOW)
        self.assertEqual([item["text"] for item in x["items"]], ["$SPY breadth is thin today"])
        self.assertEqual(x["read"], 3)  # Filtered posts still count toward the daily cap.

    def test_reddit_shows_the_most_upvoted_unpinned_posts(self):
        http = Scripted()
        record = fetch_reddit(KEYS["redditapis_token"], ["stocks", "wallstreetbets"], http_get=http, now=lambda: NOW)
        self.assertEqual([item["subreddit"] for item in record["items"]], ["wallstreetbets", "stocks"])
        self.assertNotIn("pinned", json.dumps(record))
        for _url, kwargs in http.calls:
            self.assertEqual(kwargs["headers"], {"Authorization": "Bearer " + KEYS["redditapis_token"]})
            self.assertEqual(kwargs["params"]["sort"], "hot")
        self.assertIn("On Reddit: \"wallstreetbets thread\" (r/wallstreetbets, 1400 upvotes, 40 comments)",
                      feed_lines({"headlines": {}, "x": {}, "reddit": record})[2])
        self.assertEqual(fetch_reddit(None, ["stocks"], http_get=http, now=lambda: NOW)["status"], "unavailable")

    def test_subreddit_lists_are_small_and_clean_and_the_owner_sets_them(self):
        self.assertEqual(validate_subreddits(["r/stocks", " investing", "Stocks"]), ["stocks", "investing"])
        for bad in ([], ["a"] * 6, ["bad name"], ["x"], [3], "stocks"):
            with self.subTest(bad=bad), self.assertRaises(FeedError):
                validate_subreddits(bad)
        settings = OwnerSettings(self.root / "settings")
        self.assertIsNone(settings.subreddits())
        settings.update({"subreddits": ["r/options", "Economics"]})
        self.assertEqual(settings.subreddits(), ["options", "Economics"])
        self.assertEqual(settings.read()["subreddits"], ["options", "Economics"])
        with self.assertRaises(SettingsError):
            settings.update({"subreddits": ["a b"]})

    def test_x_search_is_read_only_small_and_most_liked_first(self):
        http = Scripted()
        record = fetch_x_posts("t" * 10, ["SPY", "BRK.B", "QQQ"], http_get=http, now=lambda: NOW)
        self.assertEqual([item["likes"] for item in record["items"]], [9, 8, 7])
        (url, kwargs), = http.calls
        self.assertEqual(kwargs["params"]["max_results"], 10)
        self.assertIn("$SPY OR $QQQ", kwargs["params"]["query"])
        self.assertNotIn("BRK", kwargs["params"]["query"])  # Not a cashtag X can search.
        self.assertIn("-is:retweet", kwargs["params"]["query"])
        self.assertFalse(kwargs["allow_redirects"])

    def test_failures_and_missing_keys_say_so_without_echoing_keys(self):
        for record in (fetch_headlines(None, http_get=Scripted(), now=lambda: NOW),
                       fetch_x_posts(None, ["SPY"], http_get=Scripted(), now=lambda: NOW),
                       fetch_x_posts(KEYS["x_bearer_token"], ["SPY"], http_get=Scripted(401), now=lambda: NOW)):
            self.assertEqual(record["status"], "unavailable")
            self.assertNotIn(KEYS["x_bearer_token"], json.dumps(record))
        lines = feed_lines({"headlines": {"status": "unavailable", "reason": "no Massive key is saved"},
                            "x": {"status": "unavailable", "reason": "it answered 401"}})
        self.assertEqual(lines, ["Headlines: unavailable (no Massive key is saved).",
                                 "On X: unavailable (it answered 401)."])


class CacheTests(Blocked):
    def test_each_feed_waits_for_its_window_and_x_stops_at_the_daily_cap(self):
        start = datetime(2026, 11, 19, 0, 30, tzinfo=timezone.utc)
        clock = [start]
        http = Scripted()
        feeds = MarketFeeds(self.root, ["SPY", "QQQ"], KEYS.get, http_get=http, now=lambda: clock[0])
        first = feeds.read()
        self.assertEqual((first["headlines"]["status"], first["x"]["status"]), ("ok", "ok"))
        clock[0] = start + timedelta(minutes=59)
        feeds.read()
        self.assertEqual(len(http.calls), 7)  # News, X and five subreddits once; nothing new inside the windows.
        for hours in range(1, 12):
            clock[0] = start + timedelta(hours=2 * hours)
            feeds.read()
        x_calls = [c for c in http.calls if c[0] == X_SEARCH_URL]
        self.assertEqual(len(x_calls) * 10, X_DAILY_POST_CAP)  # Six searches, then it stops for the day.
        reddit_calls = [c for c in http.calls if c[0] == REDDIT_URL]
        self.assertEqual(len(reddit_calls), 5 * 12)  # Five subreddits, at most once every two hours.
        self.assertTrue(feeds.read()["x"]["capped"])
        self.assertIn("reading limit reached", feed_lines(feeds.read())[1])
        clock[0] = start + timedelta(days=1)
        feeds.read()
        self.assertEqual(len([c for c in http.calls if c[0] == X_SEARCH_URL]), 7)  # A new day reads again.
        record = json.loads((self.root / "x_posts.json").read_text(encoding="utf-8"))
        self.assertLessEqual(record["read_today"], X_DAILY_POST_CAP)
        self.assertEqual((self.root / "x_posts.json").stat().st_mode & 0o077, 0)
        text = feed_lines(feeds.read())
        self.assertTrue(text[0].startswith("Headlines (Massive news): Story 0 (Wire)"))
        self.assertIn("likes", text[1])


if __name__ == "__main__":
    unittest.main()
