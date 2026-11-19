"""Headlines and X posts for the market window (phase 3 of MARKET_WINDOW.md).

Read-only and shared, like the price window:

- Headlines: Massive's news endpoint, up to five, at most one fetch an hour.
- X: one recent search for the watchlist's cashtags (English, no retweets or
  replies), up to three posts shown, at most one fetch every two hours and at
  most ``X_DAILY_POST_CAP`` posts read per day. Uses the app's Bearer Token
  only, so nothing can be posted, liked or sent.

Each feed is cached in its own private file. A failed fetch is cached too, so
it waits for its next window. Nothing here is a fact: the lines are quoted to
the agents as untrusted text with the source named.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from uuid import uuid4

NEWS_URL = "https://api.massive.com/v2/reference/news"
X_SEARCH_URL = "https://api.x.com/2/tweets/search/recent"
NEWS_REFRESH_SECONDS = 60 * 60
X_REFRESH_SECONDS = 2 * 60 * 60
X_MAX_RESULTS = 10            # The smallest page X allows; each post read is billed.
X_DAILY_POST_CAP = 60         # About 30 cents a day at $0.005 per post read.
TIMEOUT_SECONDS = 10
_CASHTAG = re.compile(r"[A-Z]{1,6}")


def _now_utc(now):
    return now().astimezone(timezone.utc)


def _time(value):
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else None


def _clean(text, limit):
    text = " ".join(str(text).split())
    text = re.sub(r"https?://\S+", "", text).strip()  # Links add nothing to read here.
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def _get(http_get, url, **kwargs):
    try:
        response = http_get(url, timeout=TIMEOUT_SECONDS, allow_redirects=False, **kwargs)
    except Exception as error:
        return None, f"could not reach it ({type(error).__name__})"
    if getattr(response, "status_code", None) != 200:
        return None, f"it answered {getattr(response, 'status_code', None)}"
    try:
        return response.json(), None
    except Exception:
        return None, "it sent nothing usable"


def fetch_headlines(key, *, http_get, now):
    stamp = _now_utc(now).isoformat()
    if not key:
        return {"checked_at": stamp, "status": "unavailable", "reason": "no Massive key is saved"}
    data, problem = _get(http_get, NEWS_URL, params={"limit": 5, "order": "desc", "sort": "published_utc",
                                                     "apiKey": key})
    if problem:
        return {"checked_at": stamp, "status": "unavailable", "reason": problem}
    rows = data.get("results") if isinstance(data, dict) else None
    items = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or not isinstance(row.get("title"), str):
            continue
        publisher = row.get("publisher") if isinstance(row.get("publisher"), dict) else {}
        items.append({"title": _clean(row["title"], 160),
                      "source": _clean(publisher.get("name") or "unknown", 40),
                      "published": row.get("published_utc") if _time(row.get("published_utc")) else None})
        if len(items) == 5:
            break
    if not items:
        return {"checked_at": stamp, "status": "unavailable", "reason": "no headlines came back"}
    return {"checked_at": stamp, "status": "ok", "items": items}


def fetch_x_posts(token, symbols, *, http_get, now):
    stamp = _now_utc(now).isoformat()
    tags = [s for s in symbols if _CASHTAG.fullmatch(s)]
    if not token:
        return {"checked_at": stamp, "status": "unavailable", "reason": "no X bearer token is saved", "read": 0}
    if not tags:
        return {"checked_at": stamp, "status": "unavailable", "reason": "no tickers X can search", "read": 0}
    query = "(" + " OR ".join("$" + tag for tag in tags) + ") lang:en -is:retweet -is:reply"
    data, problem = _get(http_get, X_SEARCH_URL, headers={"Authorization": "Bearer " + token},
                         params={"query": query, "max_results": X_MAX_RESULTS,
                                 "tweet.fields": "created_at,public_metrics"})
    if problem:
        return {"checked_at": stamp, "status": "unavailable", "reason": problem, "read": 0}
    rows = data.get("data") if isinstance(data, dict) else None
    rows = [row for row in rows if isinstance(row, dict) and isinstance(row.get("text"), str)] if isinstance(rows, list) else []

    def likes(row):
        metrics = row.get("public_metrics") if isinstance(row.get("public_metrics"), dict) else {}
        value = metrics.get("like_count")
        return value if isinstance(value, int) else 0

    rows.sort(key=likes, reverse=True)
    items = [{"text": _clean(row["text"], 200), "likes": likes(row),
              "created": row.get("created_at") if _time(row.get("created_at")) else None} for row in rows[:3]]
    if not items:
        return {"checked_at": stamp, "status": "unavailable", "reason": "no recent posts found", "read": len(rows)}
    return {"checked_at": stamp, "status": "ok", "items": items, "read": len(rows), "query": query}


class _Cache:
    def __init__(self, path):
        self.path = Path(path)

    def read(self):
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            return None
        return value if isinstance(value, dict) else None

    def write(self, value):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = self.path.parent / f".{self.path.name}.{uuid4().hex}"
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(value, handle, sort_keys=True)
            os.replace(temporary, self.path)
        except BaseException:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise


class MarketFeeds:
    """``secret(slot)`` reads a saved key. ``read()`` returns both feeds, cached."""

    def __init__(self, cache_dir, symbols, secret, *, http_get=None, now=None):
        self.news = _Cache(Path(cache_dir) / "headlines.json")
        self.x = _Cache(Path(cache_dir) / "x_posts.json")
        self.symbols = list(symbols)
        self.secret = secret
        self.http_get = http_get
        self.now = now or (lambda: datetime.now(timezone.utc))

    def _http(self):
        if self.http_get is None:
            import requests
            return requests.get
        return self.http_get

    def _age(self, record):
        checked = _time((record or {}).get("checked_at"))
        return None if checked is None else (_now_utc(self.now) - checked).total_seconds()

    def _headlines(self):
        record = self.news.read()
        age = self._age(record)
        if age is not None and 0 <= age < NEWS_REFRESH_SECONDS:
            return record
        record = fetch_headlines(self.secret("massive"), http_get=self._http(), now=self.now)
        self.news.write(record)
        return record

    def _posts(self):
        record = self.x.read()
        age = self._age(record)
        today = _now_utc(self.now).date().isoformat()
        same_query = record and record.get("symbols") == self.symbols
        if age is not None and 0 <= age < X_REFRESH_SECONDS and same_query:
            return record
        read_today = (record or {}).get("read_today", 0) if (record or {}).get("day") == today else 0
        if read_today + X_MAX_RESULTS > X_DAILY_POST_CAP:
            capped = dict(record or {}, status=(record or {}).get("status", "unavailable"))
            capped["capped"] = True
            return capped  # Keep showing the last posts; read nothing more today.
        fresh = fetch_x_posts(self.secret("x_bearer_token"), self.symbols, http_get=self._http(), now=self.now)
        fresh.update(day=today, read_today=read_today + fresh.get("read", 0), symbols=self.symbols)
        self.x.write(fresh)
        return fresh

    def read(self):
        return {"headlines": self._headlines(), "x": self._posts()}


def feed_lines(feeds):
    """Short quoted lines for every choice. Never invents a headline or post."""
    lines = []
    news = (feeds or {}).get("headlines") or {}
    if news.get("status") == "ok":
        lines.append("Headlines (Massive news): " + " | ".join(
            f"{item['title']} ({item['source']})" for item in news["items"]))
    else:
        lines.append(f"Headlines: unavailable ({news.get('reason') or 'not checked yet'}).")
    posts = (feeds or {}).get("x") or {}
    if posts.get("status") == "ok" and posts.get("items"):
        lead = "On X about the watchlist" + (" (today's reading limit reached; earlier posts)" if posts.get("capped") else "")
        lines.append(lead + ": " + " | ".join(f"\"{item['text']}\" ({item['likes']} likes)" for item in posts["items"]))
    else:
        lines.append(f"On X: unavailable ({posts.get('reason') or 'not checked yet'}).")
    return lines
