"""
Polygon.io Data Feed — Paradox Edge Trader v2
=============================================
Env var: POLYGON_API_KEY

Polygon strengths:
  - Real-time and historical options data (the best free-tier options feed)
  - Options flow — unusual activity, large trades
  - Aggregated bars (OHLCV) for stocks and options
  - Snapshot data — all tickers at once
  - Market holidays and trading hours
  - Ticker details and financials
  - WebSocket support for real-time streaming (future phase)

Free tier: unlimited historical data, 5 API calls/minute real-time.
Starter ($29/mo): 15 calls/min + more options data.
Docs: https://polygon.io/docs
"""

import os
from typing import Optional

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

POLYGON_BASE = "https://api.polygon.io"


def _get_key() -> str:
    key = os.environ.get("POLYGON_API_KEY", "").strip()
    return key if key and not key.startswith("YOUR_") else ""


def _get(endpoint: str, params: Optional[dict] = None) -> dict | list:
    if not REQUESTS_AVAILABLE:
        return {"error": "requests not installed"}
    key = _get_key()
    if not key:
        return {"error": "POLYGON_API_KEY not set"}
    p = {"apiKey": key}
    if params:
        p.update(params)
    try:
        resp = requests.get(f"{POLYGON_BASE}{endpoint}", params=p, timeout=20)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def _paginate(endpoint: str, params: Optional[dict] = None, max_results: int = 100) -> list:
    """Handle Polygon's cursor-based pagination."""
    results = []
    p = params or {}
    p["limit"] = min(max_results, 250)
    url = f"{POLYGON_BASE}{endpoint}"
    key = _get_key()
    if not key:
        return []

    while url and len(results) < max_results:
        try:
            resp = requests.get(url, params={**p, "apiKey": key}, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            batch = data.get("results", [])
            results.extend(batch)
            url = data.get("next_url")
            p = {}  # next_url already has params
        except Exception:
            break
    return results[:max_results]


# ─── Stock Aggregates (OHLCV bars) ────────────────────────────────────────────

def get_aggs(symbol: str, multiplier: int = 1, timespan: str = "day",
             from_date: str = "2024-01-01", to_date: str = "2025-12-31",
             adjusted: bool = True, limit: int = 120) -> list:
    """
    Aggregate bars (OHLCV).
    timespan: minute, hour, day, week, month, quarter, year
    """
    data = _get(
        f"/v2/aggs/ticker/{symbol}/range/{multiplier}/{timespan}/{from_date}/{to_date}",
        {"adjusted": str(adjusted).lower(), "sort": "desc", "limit": limit},
    )
    return data.get("results", []) if isinstance(data, dict) else []


def get_snapshot(symbol: str) -> dict:
    """Full snapshot: current price, day OHLCV, prev day, minute bar."""
    data = _get(f"/v2/snapshot/locale/us/markets/stocks/tickers/{symbol}")
    if isinstance(data, dict):
        return data.get("ticker", data)
    return {}


def get_previous_close(symbol: str) -> dict:
    """Previous day's OHLCV."""
    data = _get(f"/v2/aggs/ticker/{symbol}/prev")
    results = data.get("results", []) if isinstance(data, dict) else []
    return results[0] if results else {}


# ─── Options Data ─────────────────────────────────────────────────────────────

def get_options_chain(underlying: str, expiration_date: Optional[str] = None,
                      contract_type: Optional[str] = None,
                      strike_price_gte: Optional[float] = None,
                      strike_price_lte: Optional[float] = None,
                      limit: int = 50) -> list:
    """
    Options contracts for an underlying ticker.
    contract_type: call or put
    expiration_date: YYYY-MM-DD
    Returns list of option contract details with Greeks if available.
    """
    params = {"underlying_ticker": underlying, "limit": limit}
    if expiration_date:
        params["expiration_date"] = expiration_date
    if contract_type:
        params["contract_type"] = contract_type
    if strike_price_gte:
        params["strike_price.gte"] = strike_price_gte
    if strike_price_lte:
        params["strike_price.lte"] = strike_price_lte

    return _paginate("/v3/reference/options/contracts", params, max_results=limit)


def get_option_snapshot(option_ticker: str) -> dict:
    """
    Real-time snapshot for a specific option contract.
    option_ticker format: O:AAPL230616C00150000
    Includes Greeks (delta, gamma, theta, vega, rho) and IV.
    """
    data = _get(f"/v3/snapshot/options/{option_ticker}")
    if isinstance(data, dict):
        return data.get("results", data)
    return {}


def get_options_snapshots(underlying: str, expiration_date: Optional[str] = None,
                          contract_type: Optional[str] = None, limit: int = 20) -> list:
    """
    Snapshots for multiple options contracts at once.
    Includes Greeks and IV for each contract.
    This is the Alchemist's primary tool.
    """
    params = {"limit": limit}
    if expiration_date:
        params["expiration_date"] = expiration_date
    if contract_type:
        params["contract_type"] = contract_type

    data = _get(f"/v3/snapshot/options/{underlying}", params)
    if isinstance(data, dict):
        return data.get("results", [])
    return []


def get_unusual_options_activity(underlying: Optional[str] = None, limit: int = 20) -> list:
    """
    Options contracts with unusually high volume relative to open interest.
    The Alchemist and Shadow both watch this for smart money signals.
    """
    params = {"limit": limit, "sort": "day.volume", "order": "desc"}
    if underlying:
        params["underlying_ticker"] = underlying
    return _paginate("/v3/snapshot/options", params, max_results=limit)


# ─── Market Status & Calendar ─────────────────────────────────────────────────

def get_market_status() -> dict:
    """Is the market currently open? Pre/post market status."""
    return _get("/v1/marketstatus/now")


def get_market_holidays() -> list:
    """Upcoming market holidays."""
    data = _get("/v1/marketstatus/upcoming")
    return data if isinstance(data, list) else []


# ─── News ─────────────────────────────────────────────────────────────────────

def get_news(ticker: Optional[str] = None, limit: int = 10) -> list:
    """
    Recent news articles. Optionally filtered by ticker.
    Includes sentiment scores (positive/negative/neutral) and relevance.
    """
    params = {"limit": limit, "order": "desc", "sort": "published_utc"}
    if ticker:
        params["ticker"] = ticker
    return _paginate("/v2/reference/news", params, max_results=limit)


# ─── Ticker Details ───────────────────────────────────────────────────────────

def get_ticker_details(symbol: str) -> dict:
    """Company details: sector, industry, description, market cap, employees."""
    data = _get(f"/v3/reference/tickers/{symbol}")
    if isinstance(data, dict):
        return data.get("results", data)
    return {}


# ─── Status ───────────────────────────────────────────────────────────────────

def is_available() -> bool:
    return bool(_get_key())
