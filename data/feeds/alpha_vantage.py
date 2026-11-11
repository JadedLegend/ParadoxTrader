"""
Alpha Vantage Data Feed — Paradox Edge Trader v2
=================================================
Reads from two Alpha Vantage API keys (rotates between them to
stay within per-key rate limits).

Env vars read (both naming conventions supported):
  ALPHA_VANTAGE_API_KEY   — key 1
  ALPHAVANTAGE_API_KEY    — key 2

Free tier: 25 requests/day per key → 50 total with two keys.
Premium tier: higher limits if keys are upgraded.

Provides:
  - Intraday & daily price data
  - RSI, MACD, Bollinger Bands, EMA technical indicators
  - Options data (premium endpoint)
  - Earnings calendar
  - Sector performance
"""

import os
import time
from typing import Optional

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

AV_BASE = "https://www.alphavantage.co/query"

# ─── Key rotation ─────────────────────────────────────────────────────────────

_key_index = 0

def _get_keys() -> list[str]:
    """Return all available Alpha Vantage keys, skipping blanks."""
    keys = []
    for var in ("ALPHA_VANTAGE_API_KEY", "ALPHAVANTAGE_API_KEY"):
        k = os.environ.get(var, "").strip()
        if k and not k.startswith("YOUR_"):
            keys.append(k)
    return keys or ["demo"]


def _get_key() -> str:
    """Rotate through available keys on each call."""
    global _key_index
    keys = _get_keys()
    key = keys[_key_index % len(keys)]
    _key_index += 1
    return key


def _get(params: dict, timeout: int = 20) -> dict:
    if not REQUESTS_AVAILABLE:
        return {"error": "requests not installed"}
    params["apikey"] = _get_key()
    try:
        resp = requests.get(AV_BASE, params=params, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        # Alpha Vantage returns error messages inside the JSON
        if "Error Message" in data:
            return {"error": data["Error Message"]}
        if "Note" in data:
            return {"error": "Rate limit hit. " + data["Note"]}
        if "Information" in data:
            return {"error": "API limit: " + data["Information"]}
        return data
    except Exception as e:
        return {"error": str(e)}


# ─── Price Data ───────────────────────────────────────────────────────────────

def get_intraday(symbol: str, interval: str = "5min", outputsize: str = "compact") -> dict:
    """
    Intraday OHLCV data.
    interval: 1min, 5min, 15min, 30min, 60min
    outputsize: compact (100 bars) or full (30 days)
    """
    return _get({
        "function": "TIME_SERIES_INTRADAY",
        "symbol": symbol,
        "interval": interval,
        "outputsize": outputsize,
    })


def get_daily(symbol: str, outputsize: str = "compact") -> dict:
    """Daily adjusted OHLCV. compact = 100 days, full = 20+ years."""
    return _get({
        "function": "TIME_SERIES_DAILY_ADJUSTED",
        "symbol": symbol,
        "outputsize": outputsize,
    })


def get_quote(symbol: str) -> dict:
    """Real-time quote for a symbol."""
    data = _get({"function": "GLOBAL_QUOTE", "symbol": symbol})
    return data.get("Global Quote", data)


# ─── Technical Indicators ─────────────────────────────────────────────────────

def get_rsi(symbol: str, interval: str = "daily", time_period: int = 14) -> dict:
    return _get({
        "function": "RSI",
        "symbol": symbol,
        "interval": interval,
        "time_period": time_period,
        "series_type": "close",
    })


def get_macd(symbol: str, interval: str = "daily") -> dict:
    return _get({
        "function": "MACD",
        "symbol": symbol,
        "interval": interval,
        "series_type": "close",
    })


def get_bbands(symbol: str, interval: str = "daily", time_period: int = 20) -> dict:
    """Bollinger Bands."""
    return _get({
        "function": "BBANDS",
        "symbol": symbol,
        "interval": interval,
        "time_period": time_period,
        "series_type": "close",
    })


def get_ema(symbol: str, interval: str = "daily", time_period: int = 20) -> dict:
    return _get({
        "function": "EMA",
        "symbol": symbol,
        "interval": interval,
        "time_period": time_period,
        "series_type": "close",
    })


def get_atr(symbol: str, interval: str = "daily", time_period: int = 14) -> dict:
    """Average True Range — volatility measure."""
    return _get({
        "function": "ATR",
        "symbol": symbol,
        "interval": interval,
        "time_period": time_period,
    })


def get_adx(symbol: str, interval: str = "daily", time_period: int = 14) -> dict:
    """Average Directional Index — trend strength."""
    return _get({
        "function": "ADX",
        "symbol": symbol,
        "interval": interval,
        "time_period": time_period,
    })


# ─── Fundamental & Macro ──────────────────────────────────────────────────────

def get_earnings_calendar(symbol: Optional[str] = None, horizon: str = "3month") -> dict:
    """Upcoming earnings. horizon: 3month, 6month, 12month."""
    params = {"function": "EARNINGS_CALENDAR", "horizon": horizon}
    if symbol:
        params["symbol"] = symbol
    return _get(params)


def get_sector_performance() -> dict:
    """Real-time sector performance (S&P 500 sectors)."""
    return _get({"function": "SECTOR"})


def get_news_sentiment(tickers: Optional[str] = None, topics: Optional[str] = None, limit: int = 10) -> dict:
    """
    News & sentiment feed.
    tickers: comma-separated e.g. "AAPL,MSFT"
    topics: e.g. "earnings,ipo,mergers_and_acquisitions,financial_markets,economy_macro"
    """
    params = {"function": "NEWS_SENTIMENT", "limit": limit}
    if tickers:
        params["tickers"] = tickers
    if topics:
        params["topics"] = topics
    return _get(params)


# ─── Composite Technical Summary ──────────────────────────────────────────────

def get_technical_summary(symbol: str) -> dict:
    """
    Pull RSI + MACD + BBands in one call sequence.
    Returns a compact dict suitable for agent context injection.
    Uses 2 of the daily key quota — call sparingly.
    """
    rsi_data = get_rsi(symbol)
    macd_data = get_macd(symbol)

    # Extract latest RSI value
    rsi_series = rsi_data.get("Technical Analysis: RSI", {})
    latest_rsi_date = next(iter(rsi_series), None)
    rsi_val = float(rsi_series[latest_rsi_date]["RSI"]) if latest_rsi_date else None

    # Extract latest MACD values
    macd_series = macd_data.get("Technical Analysis: MACD", {})
    latest_macd_date = next(iter(macd_series), None)
    macd_val = None
    macd_signal = None
    macd_hist = None
    if latest_macd_date:
        m = macd_series[latest_macd_date]
        macd_val = float(m.get("MACD", 0))
        macd_signal = float(m.get("MACD_Signal", 0))
        macd_hist = float(m.get("MACD_Hist", 0))

    return {
        "symbol": symbol,
        "rsi_14": rsi_val,
        "rsi_signal": (
            "overbought" if rsi_val and rsi_val > 70 else
            "oversold" if rsi_val and rsi_val < 30 else
            "neutral"
        ),
        "macd": macd_val,
        "macd_signal": macd_signal,
        "macd_histogram": macd_hist,
        "macd_crossover": (
            "bullish" if macd_hist and macd_hist > 0 else
            "bearish" if macd_hist and macd_hist < 0 else
            "neutral"
        ),
        "keys_available": len(_get_keys()),
    }
