"""Daily closing prices, for settling calls (phase 2 of docs/specs/CALLS_AND_SETTLEMENT.md).

- One kind of GET only: Alpaca's market data daily bars, free IEX feed, read
  with the same paper data key the market window uses. Never a trading
  endpoint, and never core/trading/alpaca.py, which can place orders.
- Each bar's date is its US Eastern trading session. The sessions that come
  back are the trading calendar, so holidays need no hand-kept list.
- Never raises for data trouble: an answer it cannot use is "unavailable" with
  a short reason, and every close is a number the response gave or is absent.
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation
import re

BARS_URL = "https://data.alpaca.markets/v2/stocks/bars"
TIMEOUT_SECONDS = 10
MAX_PAGES = 5
_PAPER_KEY = re.compile(r"PK[A-Z0-9]{8,40}")


def _eastern_date(value):
    """The Eastern date of a bar time such as 2026-11-20T05:00:00Z."""
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        return None
    from core.runtime.rehearsal.calls import _session
    return _session(moment)


def _close(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        return None
    return amount if amount.is_finite() and amount > 0 else None


def fetch_closes(symbols, start, end, key_id, secret, *, http_get):
    """Daily closes from ``start`` to ``end`` (Eastern dates, inclusive).

    Returns ``{"status": "ok", "closes": {symbol: {date: Decimal}}}`` or
    ``{"status": "unavailable", "reason": ...}``. A symbol with no bars is
    simply missing from ``closes``."""
    if not (isinstance(key_id, str) and _PAPER_KEY.fullmatch(key_id) and isinstance(secret, str) and secret):
        return {"status": "unavailable", "reason": "no Alpaca paper key is saved"}
    params = {"symbols": ",".join(symbols), "timeframe": "1Day", "start": start, "end": end,
              "feed": "iex", "adjustment": "raw", "limit": 10000}
    headers = {"APCA-API-KEY-ID": key_id, "APCA-API-SECRET-KEY": secret}
    closes = {}
    for _ in range(MAX_PAGES):
        try:
            response = http_get(BARS_URL, params=params, headers=headers, timeout=TIMEOUT_SECONDS,
                                allow_redirects=False)
        except Exception as error:  # Network trouble: say so, never raise into the heartbeat.
            return {"status": "unavailable", "reason": f"could not reach market data ({type(error).__name__})"}
        status = getattr(response, "status_code", None)
        if status != 200:
            return {"status": "unavailable", "reason": f"market data answered {status}"}
        try:
            data = response.json()
        except Exception:
            data = None
        bars = data.get("bars") if isinstance(data, dict) else None
        if not isinstance(bars, dict):
            return {"status": "unavailable", "reason": "market data sent nothing usable"}
        for symbol, rows in bars.items():
            if symbol not in symbols or not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                session, price = _eastern_date(row.get("t")), _close(row.get("c"))
                if session is not None and price is not None and start <= session <= end:
                    closes.setdefault(symbol, {})[session] = price
        token = data.get("next_page_token")
        if not isinstance(token, str) or not token:
            return {"status": "ok", "closes": closes}
        params = {**params, "page_token": token}
    return {"status": "unavailable", "reason": "market data sent too many pages"}
