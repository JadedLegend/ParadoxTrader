"""The market window: a small, shared, read-only price snapshot.

Phase 1 of docs/specs/MARKET_WINDOW.md.

- One GET only: Alpaca's market data snapshots endpoint, free IEX feed. This
  module never touches a trading endpoint and does not reuse
  core/trading/alpaca.py, which can place orders.
- At most one fetch per ``REFRESH_SECONDS``, shared by every agent and cached
  as one private JSON file. A failed fetch is cached as "unavailable" too, so
  it is not retried until the next window.
- At most ``MAX_SYMBOLS`` symbols; every number comes from the response or is
  left out. When the data is old (market closed) the window says so.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import re
from uuid import uuid4

DATA_URL = "https://data.alpaca.markets/v2/stocks/snapshots"
DEFAULT_WATCHLIST = ("SPY", "QQQ", "IWM", "TLT", "GLD")
MAX_SYMBOLS = 5
REFRESH_SECONDS = 15 * 60
TIMEOUT_SECONDS = 10
FRESH_TRADE_SECONDS = 30 * 60  # Older than this during a fetch: the market is closed.
_SYMBOL = re.compile(r"[A-Z]{1,5}(?:[.][A-Z]{1,2})?")
_PAPER_KEY = re.compile(r"PK[A-Z0-9]{8,40}")


class MarketWindowError(ValueError):
    """A watchlist or key that the window refuses."""


def validate_symbols(symbols):
    """A clean, unique list of 1-5 ticker symbols, upper-cased."""
    if not isinstance(symbols, (list, tuple)) or not 1 <= len(symbols) <= MAX_SYMBOLS:
        raise MarketWindowError("invalid_watchlist")
    clean = []
    for symbol in symbols:
        if not isinstance(symbol, str):
            raise MarketWindowError("invalid_watchlist")
        symbol = symbol.strip().upper()
        if not _SYMBOL.fullmatch(symbol):
            raise MarketWindowError("invalid_ticker")
        if symbol not in clean:
            clean.append(symbol)
    return clean


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        return None
    return amount if amount.is_finite() else None


def _time(value):
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else None


def _quote(symbol, row):
    """One symbol's figures, only those the response actually gave."""
    if not isinstance(row, dict):
        return None
    trade = row.get("latestTrade") if isinstance(row.get("latestTrade"), dict) else {}
    bar = row.get("dailyBar") if isinstance(row.get("dailyBar"), dict) else {}
    previous = row.get("prevDailyBar") if isinstance(row.get("prevDailyBar"), dict) else {}
    last = _number(trade.get("p")) or _number(bar.get("c"))
    if last is None or last <= 0:
        return None
    quote = {"symbol": symbol, "last": float(last)}
    for key, field in (("open", "o"), ("high", "h"), ("low", "l"), ("volume", "v")):
        value = _number(bar.get(field))
        if value is not None:
            quote[key] = float(value) if key != "volume" else int(value)
    before = _number(previous.get("c"))
    if before is not None and before > 0:
        quote["change_percent"] = float(((last - before) / before * 100).quantize(Decimal("0.01")))
    moment = _time(trade.get("t")) or _time(bar.get("t"))
    return quote, moment


def fetch(symbols, key_id, secret, *, http_get, now, account=None):
    """One snapshot GET. Returns the window record; never raises for data trouble.

    Each price keeps its own time (``as_of``), so one fresh ticker cannot make a
    stale one look current; a price with no time of its own is marked so rather
    than given the fetch time. ``account`` labels the data account, never a key."""
    stamp = now().astimezone(timezone.utc)
    base = {"checked_at": stamp.isoformat(), "symbols": list(symbols), "source": "alpaca-iex", "account": account}
    if not (isinstance(key_id, str) and _PAPER_KEY.fullmatch(key_id) and isinstance(secret, str) and secret):
        return {**base, "status": "unavailable", "reason": "no Alpaca paper key is saved"}
    try:
        response = http_get(DATA_URL, params={"symbols": ",".join(symbols), "feed": "iex"},
                            headers={"APCA-API-KEY-ID": key_id, "APCA-API-SECRET-KEY": secret},
                            timeout=TIMEOUT_SECONDS, allow_redirects=False)
    except Exception as error:  # Network trouble: say so, never raise into a wake.
        return {**base, "status": "unavailable", "reason": f"could not reach market data ({type(error).__name__})"}
    status = getattr(response, "status_code", None)
    if status != 200:
        return {**base, "status": "unavailable", "reason": f"market data answered {status}"}
    try:
        data = response.json()
    except Exception:
        data = None
    rows = data.get("snapshots", data) if isinstance(data, dict) else None
    if not isinstance(rows, dict):
        return {**base, "status": "unavailable", "reason": "market data sent nothing usable"}
    quotes, latest = [], None
    for symbol in symbols:
        parsed = _quote(symbol, rows.get(symbol))
        if parsed is None:
            continue
        quote, moment = parsed
        if moment is not None and moment <= stamp + timedelta(minutes=5):  # Future-dated times are not trusted.
            quote["as_of"] = moment.astimezone(timezone.utc).isoformat()
            if latest is None or moment > latest:
                latest = moment
        quotes.append(quote)
    if not quotes:
        return {**base, "status": "unavailable", "reason": "no prices for these tickers"}
    state = "open" if latest is not None and (stamp - latest).total_seconds() <= FRESH_TRADE_SECONDS else "closed"
    for quote in quotes:
        moment = _time(quote.get("as_of"))
        quote["stale"] = moment is None or (state == "open" and (stamp - moment).total_seconds() > FRESH_TRADE_SECONDS)
    record = {**base, "status": state, "quotes": quotes}
    if latest is not None:
        record["as_of"] = latest.astimezone(timezone.utc).isoformat()
    return record


class MarketWindow:
    """The shared cached window. ``credentials()`` returns (key_id, secret) or None."""

    def __init__(self, cache_dir, symbols, credentials, *, http_get=None, now=None):
        self.path = Path(cache_dir) / "window.json"
        self.symbols = validate_symbols(list(symbols))
        self.credentials = credentials
        self.http_get = http_get
        self.now = now or (lambda: datetime.now(timezone.utc))

    def cached(self):
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            return None
        return value if isinstance(value, dict) else None

    def _fresh(self, record):
        checked = _time((record or {}).get("checked_at"))
        if checked is None or record.get("symbols") != self.symbols:
            return False
        age = (self.now() - checked).total_seconds()
        return 0 <= age < REFRESH_SECONDS

    def read(self):
        """The current window: the cache when fresh, else one new fetch."""
        record = self.cached()
        if self._fresh(record):
            return record
        given = tuple(self.credentials() or ()) + (None, None, None)  # (key_id, secret[, account label])
        http_get = self.http_get
        if http_get is None:
            import requests
            http_get = requests.get
        record = fetch(self.symbols, given[0], given[1], http_get=http_get, now=self.now, account=given[2])
        self._write(record)
        return record

    def _write(self, record):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = self.path.parent / f".{self.path.name}.{uuid4().hex}"
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(record, handle, sort_keys=True)
            os.replace(temporary, self.path)
        except BaseException:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise


def _eastern(moment):
    try:
        from zoneinfo import ZoneInfo
        return moment.astimezone(ZoneInfo("America/New_York")).strftime("%b %d %H:%M ET")
    except Exception:
        return moment.strftime("%b %d %H:%M UTC")


def window_line(record):
    """One plain line for every choice. Never invents a figure."""
    if not record or record.get("status") not in ("open", "closed") or not record.get("quotes"):
        reason = (record or {}).get("reason") or "not checked yet"
        return f"Market window: unavailable ({reason})."
    as_of = _time(record.get("as_of"))
    when = _eastern(as_of) if as_of else "unknown time"
    parts = []
    for quote in record["quotes"]:
        text = f"{quote['symbol']} {quote['last']:g}"
        if "change_percent" in quote:
            text += f" ({quote['change_percent']:+.2f}%)"
        if quote.get("stale"):
            text += " (old price)" if quote.get("as_of") else " (time unknown)"
        parts.append(text)
    lead = "Market window" if record["status"] == "open" else "Market window (market closed, last prices)"
    return f"{lead} as of {when}, IEX feed, may be delayed: " + ", ".join(parts) + "."


def inquiry_evidence(record):
    """The inquire slot's market_data: status plus up to five quotes."""
    if not record or record.get("status") not in ("open", "closed") or not record.get("quotes"):
        return {"status": "unavailable"}
    quotes = []
    for quote in record["quotes"][:MAX_SYMBOLS]:
        item = {key: quote[key] for key in ("symbol", "last", "open", "high", "low", "volume", "as_of") if key in quote}
        if "change_percent" in quote:
            item["change_percent"] = quote["change_percent"]
        quotes.append(item)
    return {"status": "ok" if record["status"] == "open" else "closed", "source": "alpaca-iex",
            "quotes": quotes}
