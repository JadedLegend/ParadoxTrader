"""
Finnhub Data Feed — Paradox Edge Trader v2
===========================================
Env var: FINNHUB_API_KEY

Finnhub strengths:
  - Real-time quotes and candles
  - Earnings surprises and calendars
  - Insider transactions (buy/sell by executives)
  - Analyst price targets and recommendations
  - News sentiment with relevance scoring
  - Economic calendar (macro events)
  - IPO calendar
  - Company financials

Free tier: 60 API calls/minute — generous for our use case.
Docs: https://finnhub.io/docs/api
"""

import os
from typing import Optional

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

FINNHUB_BASE = "https://finnhub.io/api/v1"


def _get_key() -> str:
    key = os.environ.get("FINNHUB_API_KEY", "").strip()
    return key if key and not key.startswith("YOUR_") else ""


def _get(endpoint: str, params: Optional[dict] = None) -> dict | list:
    if not REQUESTS_AVAILABLE:
        return {"error": "requests not installed"}
    key = _get_key()
    if not key:
        return {"error": "FINNHUB_API_KEY not set"}
    p = {"token": key}
    if params:
        p.update(params)
    try:
        resp = requests.get(f"{FINNHUB_BASE}{endpoint}", params=p, timeout=20)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


# ─── Quote & Candles ──────────────────────────────────────────────────────────

def get_quote(symbol: str) -> dict:
    """Real-time quote: current price, open, high, low, prev close."""
    data = _get("/quote", {"symbol": symbol})
    if "error" not in data:
        return {
            "symbol": symbol,
            "price": data.get("c"),          # current
            "open": data.get("o"),
            "high": data.get("h"),
            "low": data.get("l"),
            "prev_close": data.get("pc"),
            "change": data.get("d"),
            "change_pct": data.get("dp"),
            "timestamp": data.get("t"),
        }
    return data


def get_candles(symbol: str, resolution: str = "D",
                from_ts: Optional[int] = None, to_ts: Optional[int] = None) -> dict:
    """
    OHLCV candles.
    resolution: 1, 5, 15, 30, 60, D, W, M
    from_ts / to_ts: Unix timestamps. Defaults to last 30 days.
    """
    import time
    now = int(time.time())
    params = {
        "symbol": symbol,
        "resolution": resolution,
        "from": from_ts or (now - 30 * 86400),
        "to": to_ts or now,
    }
    return _get("/stock/candle", params)


# ─── Earnings ─────────────────────────────────────────────────────────────────

def get_earnings_surprises(symbol: str, limit: int = 8) -> list:
    """
    Historical earnings surprises — actual vs estimated EPS.
    Useful for the Oracle's pattern recognition.
    """
    data = _get("/stock/earnings", {"symbol": symbol, "limit": limit})
    return data if isinstance(data, list) else []


def get_earnings_calendar(from_date: str, to_date: str) -> dict:
    """
    Upcoming earnings releases.
    from_date / to_date: YYYY-MM-DD format.
    """
    return _get("/calendar/earnings", {"from": from_date, "to": to_date})


# ─── Insider Transactions ─────────────────────────────────────────────────────

def get_insider_transactions(symbol: str) -> dict:
    """
    Recent insider buy/sell transactions.
    The Shadow loves this — insiders selling is a structural weakness signal.
    """
    return _get("/stock/insider-transactions", {"symbol": symbol})


def get_insider_sentiment(symbol: str, from_date: str, to_date: str) -> dict:
    """
    Aggregated insider sentiment score (MSPR: Monthly Share Purchase Ratio).
    Positive = net buying, Negative = net selling.
    """
    return _get("/stock/insider-sentiment", {
        "symbol": symbol,
        "from": from_date,
        "to": to_date,
    })


# ─── Analyst Data ─────────────────────────────────────────────────────────────

def get_price_target(symbol: str) -> dict:
    """
    Analyst consensus price target — high, low, mean, median.
    Useful for the Alchemist's asymmetry calculations.
    """
    return _get("/stock/price-target", {"symbol": symbol})


def get_recommendation_trends(symbol: str) -> list:
    """
    Analyst recommendation trends: strong buy, buy, hold, sell, strong sell counts.
    """
    data = _get("/stock/recommendation", {"symbol": symbol})
    return data if isinstance(data, list) else []


# ─── News & Sentiment ─────────────────────────────────────────────────────────

def get_company_news(symbol: str, from_date: str, to_date: str) -> list:
    """
    Recent news articles for a symbol with sentiment.
    from_date / to_date: YYYY-MM-DD
    """
    data = _get("/company-news", {
        "symbol": symbol,
        "from": from_date,
        "to": to_date,
    })
    return data if isinstance(data, list) else []


def get_market_news(category: str = "general") -> list:
    """
    General market news.
    category: general, forex, crypto, merger
    """
    data = _get("/news", {"category": category})
    return data if isinstance(data, list) else []


def get_news_sentiment(symbol: str) -> dict:
    """
    Aggregated news sentiment score for a symbol.
    Returns buzz score, sentiment score, and article counts.
    """
    return _get("/news-sentiment", {"symbol": symbol})


# ─── Macro / Economic Calendar ────────────────────────────────────────────────

def get_economic_calendar() -> dict:
    """
    Upcoming economic events: Fed meetings, CPI releases, jobs reports, etc.
    The Oracle's primary macro timing tool.
    """
    return _get("/calendar/economic")


# ─── Support / Resistance ─────────────────────────────────────────────────────

def get_support_resistance(symbol: str, resolution: str = "D") -> dict:
    """
    Technical support and resistance levels.
    Useful for the Alchemist's entry/exit structuring.
    """
    return _get("/scan/support-resistance", {
        "symbol": symbol,
        "resolution": resolution,
    })


def get_aggregate_indicators(symbol: str, resolution: str = "D") -> dict:
    """
    Aggregate technical indicator signal: buy / neutral / sell.
    Quick consensus signal for the Tempest.
    """
    return _get("/scan/technical-indicator", {
        "symbol": symbol,
        "resolution": resolution,
    })


# ─── Status ───────────────────────────────────────────────────────────────────

def is_available() -> bool:
    return bool(_get_key())
