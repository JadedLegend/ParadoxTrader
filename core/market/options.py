"""The options view: a small, shared, read-only look at one ticker's options.

Phase 1 of docs/specs/OPTIONS_VIEW.md.

- One GET only: Alpaca's options snapshots endpoint on the market data host,
  with the free indicative feed. Alpaca says that feed adjusts quotes and delays
  trades, so every line and record says "indicative, delayed".
- The two nearest expiries at least a day out; at each, the at-the-money call
  and put plus the next strike out on each side. At most ``MAX_CONTRACTS``.
- Each contract keeps its own quote time. The record keeps the fetch time,
  the feed, the source and the data account's label, never a key.
- At most one fetch per ``REFRESH_SECONDS``, only during market hours, shared
  and cached; a failure waits for its next window. Nothing is invented.
"""
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import re
from uuid import uuid4
from zoneinfo import ZoneInfo

SNAPSHOTS_URL = "https://data.alpaca.markets/v1beta1/options/snapshots/{symbol}"
FEED = "indicative"
REFRESH_SECONDS = 30 * 60
TIMEOUT_SECONDS = 10
MAX_CONTRACTS = 10
STRIKE_BAND = Decimal("0.02")      # Strikes within 2% of the price.
EXPIRY_DAYS = 14                    # Look this far ahead for the two nearest expiries.
STALE_QUOTE_SECONDS = 30 * 60
EASTERN = ZoneInfo("America/New_York")
_OCC = re.compile(r"([A-Z]{1,6})(\d{6})([CP])(\d{8})")
_PAPER_KEY = re.compile(r"PK[A-Z0-9]{8,40}")
_SYMBOL = re.compile(r"[A-Z]{1,5}")


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        return None
    return amount if amount.is_finite() else None


def _time(value):
    """ISO time with any number of fractional digits (Alpaca sends nanoseconds)."""
    if not isinstance(value, str):
        return None
    text = value.replace("Z", "+00:00")
    text = re.sub(r"(\.\d{6})\d+", r"\1", text)
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    return moment if moment.tzinfo else None


def market_open(moment):
    """Regular US equity-options hours, weekdays 9:30 to 16:00 Eastern (holidays not modelled)."""
    local = moment.astimezone(EASTERN)
    return local.weekday() < 5 and time(9, 30) <= local.time() < time(16, 0)


def _contract(occ, row):
    matched = _OCC.fullmatch(occ)
    if not matched or not isinstance(row, dict):
        return None
    _, yymmdd, kind, strike = matched.groups()
    try:
        expiry = date(2000 + int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:]))
    except ValueError:
        return None
    quote = row.get("latestQuote") if isinstance(row.get("latestQuote"), dict) else {}
    bid, ask = _number(quote.get("bp")), _number(quote.get("ap"))
    if bid is None or ask is None or bid < 0 or ask <= 0 or ask < bid:
        return None
    item = {"symbol": occ, "type": "call" if kind == "C" else "put",
            "strike": float(Decimal(strike) / 1000), "expiration": expiry.isoformat(),
            "bid": float(bid), "ask": float(ask)}
    quoted = _time(quote.get("t"))
    if quoted is not None:
        item["quote_time"] = quoted.astimezone(timezone.utc).isoformat()
    iv = _number(row.get("impliedVolatility"))
    if iv is not None and iv > 0:
        item["iv"] = float(iv.quantize(Decimal("0.0001")))
    greeks = row.get("greeks") if isinstance(row.get("greeks"), dict) else {}
    delta = _number(greeks.get("delta"))
    if delta is not None:
        item["delta"] = float(delta.quantize(Decimal("0.0001")))
    return item


def _pick(contracts, price):
    """Two nearest expiries; at each the ATM pair and the next strike out each side."""
    by_expiry = {}
    for item in contracts:
        by_expiry.setdefault(item["expiration"], []).append(item)
    chosen = []
    for expiry in sorted(by_expiry)[:2]:
        rows = by_expiry[expiry]
        calls = {r["strike"]: r for r in rows if r["type"] == "call"}
        puts = {r["strike"]: r for r in rows if r["type"] == "put"}
        paired = sorted(set(calls) & set(puts))
        if not paired:
            continue
        atm = min(paired, key=lambda strike: (abs(Decimal(str(strike)) - price), strike))
        chosen += [calls[atm], puts[atm]]
        above = [s for s in sorted(calls) if s > atm]
        below = [s for s in sorted(puts) if s < atm]
        if above:
            chosen.append(calls[above[0]])
        if below:
            chosen.append(puts[below[-1]])
    return chosen[:MAX_CONTRACTS]


def fetch(symbol, price, key_id, secret, account, *, http_get, now, underlying_as_of=None):
    """One snapshots GET for ``symbol`` around ``price``. Never raises for data trouble."""
    stamp = now().astimezone(timezone.utc)
    base = {"checked_at": stamp.isoformat(), "symbol": symbol, "feed": FEED, "source": "alpaca-options",
            "account": account}
    if price is None or price <= 0:
        return {**base, "status": "unavailable", "reason": f"no current price for {symbol}"}
    if not (isinstance(key_id, str) and _PAPER_KEY.fullmatch(key_id) and isinstance(secret, str) and secret):
        return {**base, "status": "unavailable", "reason": "no Alpaca paper key is saved for the data account"}
    today = stamp.astimezone(EASTERN).date()
    params = {"feed": FEED, "limit": 1000,
              "expiration_date_gte": (today + timedelta(days=1)).isoformat(),
              "expiration_date_lte": (today + timedelta(days=EXPIRY_DAYS)).isoformat(),
              "strike_price_gte": str((price * (1 - STRIKE_BAND)).quantize(Decimal("0.01"))),
              "strike_price_lte": str((price * (1 + STRIKE_BAND)).quantize(Decimal("0.01")))}
    try:
        response = http_get(SNAPSHOTS_URL.format(symbol=symbol), params=params,
                             headers={"APCA-API-KEY-ID": key_id, "APCA-API-SECRET-KEY": secret},
                             timeout=TIMEOUT_SECONDS, allow_redirects=False)
    except Exception as error:
        return {**base, "status": "unavailable", "reason": f"could not reach options data ({type(error).__name__})"}
    if getattr(response, "status_code", None) != 200:
        return {**base, "status": "unavailable", "reason": f"options data answered {getattr(response, 'status_code', None)}"}
    try:
        data = response.json()
    except Exception:
        data = None
    rows = data.get("snapshots") if isinstance(data, dict) else None
    if not isinstance(rows, dict):
        return {**base, "status": "unavailable", "reason": "options data sent nothing usable"}
    contracts = [c for c in (_contract(occ, row) for occ, row in rows.items()) if c is not None]
    chosen = _pick(contracts, price)
    if not chosen:
        return {**base, "status": "unavailable", "reason": "no quoted contracts near the price"}
    for item in chosen:
        quoted = _time(item.get("quote_time"))
        item["stale"] = quoted is None or (stamp - quoted).total_seconds() > STALE_QUOTE_SECONDS
    state = "open" if market_open(stamp) and not all(item["stale"] for item in chosen) else "closed"
    record = {**base, "status": state, "underlying_price": float(price), "contracts": chosen}
    priced = _time(underlying_as_of)
    if priced is not None:
        record["underlying_as_of"] = priced.astimezone(timezone.utc).isoformat()
    return record


class OptionsView:
    """Shared cached options record. ``credentials()`` returns (key_id, secret, label) or None;
    ``price()`` returns the underlying's price and its own timestamp (either can be None)."""

    def __init__(self, cache_dir, symbol, credentials, price, *, http_get=None, now=None):
        if not isinstance(symbol, str) or not _SYMBOL.fullmatch(symbol):
            raise ValueError("invalid_options_symbol")
        self.path = Path(cache_dir) / "options.json"
        self.symbol, self.credentials, self.price = symbol, credentials, price
        self.http_get = http_get
        self.now = now or (lambda: datetime.now(timezone.utc))

    def cached(self):
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            return None
        return value if isinstance(value, dict) else None

    def read(self):
        record = self.cached()
        if record is not None and record.get("symbol") != self.symbol:
            record = None
        moment = self.now()
        checked = _time((record or {}).get("checked_at"))
        if not market_open(moment):
            if record is None:
                return {"symbol": self.symbol, "status": "unavailable", "feed": FEED,
                        "reason": "market closed and no options read yet"}
            return dict(record, status="closed") if record.get("contracts") else record
        if checked is not None and 0 <= (moment - checked).total_seconds() < REFRESH_SECONDS:
            return record
        given = self.credentials() or (None, None, None)
        http_get = self.http_get
        if http_get is None:
            import requests
            http_get = requests.get
        try:
            price, as_of = self.price()
        except Exception:
            price, as_of = None, None
        record = fetch(self.symbol, _number(price), given[0], given[1], given[2],
                       http_get=http_get, now=self.now, underlying_as_of=as_of)
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


def _short_date(iso, today):
    day = date.fromisoformat(iso)
    days = (day - today).days
    return f"{day.strftime('%b')} {day.day} ({days} day{'s' if days != 1 else ''})"


def options_line(record, *, now=None):
    """One plain line for every choice. Never invents a figure."""
    symbol = (record or {}).get("symbol") or "Options"
    if not record or record.get("status") not in ("open", "closed") or not record.get("contracts"):
        return f"{symbol} options: unavailable ({(record or {}).get('reason') or 'not read yet'})."
    today = (now() if now else datetime.now(timezone.utc)).astimezone(EASTERN).date()
    times = [_time(c.get("quote_time")) for c in record["contracts"]]
    latest = max((t for t in times if t is not None), default=None)
    when = latest.astimezone(EASTERN).strftime("%b %d %H:%M ET") if latest else "unknown time"
    lead = f"{symbol} options (Alpaca indicative feed, delayed"
    lead += ", market closed, last quotes" if record["status"] == "closed" else ""
    lead += f", quotes as of {when})"
    parts = []
    for expiry in sorted({c["expiration"] for c in record["contracts"]}):
        rows = [c for c in record["contracts"] if c["expiration"] == expiry]
        bits = []
        for c in rows:
            text = f"{c['type']} {c['strike']:g} {c['bid']:g}/{c['ask']:g}"
            if "iv" in c:
                text += f" IV {c['iv'] * 100:.1f}%"
            if c.get("stale"):
                text += " (old quote)"
            bits.append(text)
        parts.append(f"{_short_date(expiry, today)}: " + ", ".join(bits))
    return (lead + ": " + "; ".join(parts) + ".")[:700]


def options_at_decision(record, moment):
    """Copy cached contracts and freeze their freshness at the decision time."""
    if not record or not record.get("contracts"):
        return record
    contracts = []
    for contract in record["contracts"]:
        quoted = _time(contract.get("quote_time"))
        stale = quoted is None or not 0 <= (moment - quoted).total_seconds() <= STALE_QUOTE_SECONDS
        contracts.append(dict(contract, stale=bool(contract.get("stale")) or stale))
    return dict(record, contracts=contracts)


def options_evidence(record):
    """The inquire slot's options: status plus up to MAX_CONTRACTS contracts."""
    if not record or record.get("status") not in ("open", "closed") or not record.get("contracts"):
        return {"status": "unavailable"}
    contracts = []
    for c in record["contracts"][:MAX_CONTRACTS]:
        contracts.append({key: c[key] for key in ("symbol", "type", "strike", "expiration", "bid", "ask",
                                                  "iv", "delta", "quote_time") if key in c})
    return {"status": "ok" if record["status"] == "open" else "closed", "source": "alpaca-options indicative delayed",
            "contracts": contracts}
