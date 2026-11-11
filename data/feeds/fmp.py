"""
Financial Modeling Prep (FMP) Data Feed — Paradox Edge Trader v2
=================================================================
Provides market data, options chains, earnings calendars, macro data,
and sentiment feeds via FMP's API.

Free tier endpoints are used where possible.
Premium endpoints are gated behind key availability.
"""

import os
from typing import Optional

try:
    import requests
except ImportError:
    requests = None  # type: ignore

from core.runtime.config import load_config

FMP_BASE = "https://financialmodelingprep.com/api"


def _get_key() -> str:
    cfg = load_config()
    key = cfg.get("fmp", {}).get("api_key", "")
    if not key or key.startswith("YOUR_"):
        key = os.environ.get("FMP_API_KEY", "demo")
    return key


def _get(endpoint: str, params: Optional[dict] = None) -> dict | list:
    if requests is None:
        raise ImportError("requests required")
    key = _get_key()
    p = {"apikey": key}
    if params:
        p.update(params)
    resp = requests.get(f"{FMP_BASE}{endpoint}", params=p, timeout=30)
    resp.raise_for_status()
    return resp.json()


# ─── Quote & Price ────────────────────────────────────────────────────────────

def get_quote(symbol: str) -> dict:
    data = _get(f"/v3/quote/{symbol}")
    return data[0] if data else {}


def get_batch_quotes(symbols: list[str]) -> list[dict]:
    joined = ",".join(symbols)
    return _get(f"/v3/quote/{joined}")


def get_historical_prices(symbol: str, from_date: str, to_date: str) -> list[dict]:
    data = _get(f"/v3/historical-price-full/{symbol}", {"from": from_date, "to": to_date})
    return data.get("historical", [])


# ─── Options ─────────────────────────────────────────────────────────────────

def get_options_chain(symbol: str) -> list[dict]:
    return _get(f"/v3/options/{symbol}")


def get_options_by_expiry(symbol: str, expiry: str) -> list[dict]:
    return _get(f"/v3/options/{symbol}", {"expiration": expiry})


# ─── Earnings ─────────────────────────────────────────────────────────────────

def get_earnings_calendar(from_date: str, to_date: str) -> list[dict]:
    return _get("/v3/earning_calendar", {"from": from_date, "to": to_date})


def get_earnings_history(symbol: str) -> list[dict]:
    return _get(f"/v3/historical/earning_calendar/{symbol}")


# ─── Macro & Sector ───────────────────────────────────────────────────────────

def get_sector_performance() -> list[dict]:
    return _get("/v3/sectors-performance")


def get_market_risk_premium() -> list[dict]:
    return _get("/v4/market_risk_premium")


def get_economic_indicators(name: str) -> list[dict]:
    """
    name examples: GDP, realGDP, inflationRate, federalFunds, CPI, unemployment
    """
    return _get(f"/v4/economic", {"name": name})


# ─── Sentiment & News ─────────────────────────────────────────────────────────

def get_stock_news(symbol: str, limit: int = 10) -> list[dict]:
    return _get("/v3/stock_news", {"tickers": symbol, "limit": limit})


def get_general_news(limit: int = 10) -> list[dict]:
    return _get("/v4/general_news", {"page": 0})


def get_social_sentiment(symbol: str) -> list[dict]:
    return _get("/v4/social-sentiments/trending", {"type": "bullish", "source": "stocktwits"})


# ─── Volatility ───────────────────────────────────────────────────────────────

def get_iv_rank(symbol: str) -> dict:
    """Implied volatility rank — premium endpoint, returns empty on free tier."""
    try:
        data = _get(f"/v4/options-iv-rank/{symbol}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


# ─── Screener ─────────────────────────────────────────────────────────────────

def screen_stocks(
    market_cap_more_than: Optional[int] = None,
    volume_more_than: Optional[int] = None,
    sector: Optional[str] = None,
    limit: int = 20,
) -> list[dict]:
    params = {"limit": limit}
    if market_cap_more_than:
        params["marketCapMoreThan"] = market_cap_more_than
    if volume_more_than:
        params["volumeMoreThan"] = volume_more_than
    if sector:
        params["sector"] = sector
    return _get("/v3/stock-screener", params)
