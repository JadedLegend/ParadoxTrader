"""
Apify Yahoo Finance Feed — Paradox Edge Trader v2
==================================================
Uses the Apify Yahoo Finance actor for reliable, structured data.
Falls back to raw yfinance library if APIFY_API_KEY is not set.

Env var: APIFY_API_KEY

Apify actor used: "apify/yahoo-finance-scraper"
Docs: https://apify.com/apify/yahoo-finance-scraper

Provides:
  - Real-time quotes (more reliable than yfinance)
  - Options chains (calls + puts with full Greeks)
  - Historical OHLCV
  - Key statistics and financials
"""

import os
import time
from typing import Optional

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

APIFY_BASE = "https://api.apify.com/v2"


def _get_apify_key() -> Optional[str]:
    key = os.environ.get("APIFY_API_KEY", "").strip()
    return key if key and not key.startswith("YOUR_") else None


def _run_actor(actor_id: str, run_input: dict, timeout_secs: int = 60) -> Optional[list]:
    """
    Run an Apify actor synchronously and return the dataset items.
    Returns None on failure.
    """
    if not REQUESTS_AVAILABLE:
        return None
    key = _get_apify_key()
    if not key:
        return None

    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    # Start the actor run
    try:
        resp = requests.post(
            f"{APIFY_BASE}/acts/{actor_id}/runs",
            json=run_input,
            headers=headers,
            params={"timeout": timeout_secs, "waitForFinish": timeout_secs},
            timeout=timeout_secs + 10,
        )
        resp.raise_for_status()
        run_data = resp.json().get("data", {})
        dataset_id = run_data.get("defaultDatasetId")
        if not dataset_id:
            return None

        # Fetch dataset items
        items_resp = requests.get(
            f"{APIFY_BASE}/datasets/{dataset_id}/items",
            headers=headers,
            params={"format": "json", "clean": True},
            timeout=30,
        )
        items_resp.raise_for_status()
        return items_resp.json()
    except Exception:
        return None


# ─── Quote ────────────────────────────────────────────────────────────────────

def get_quote(symbol: str) -> dict:
    """
    Real-time quote. Uses Apify if key available, else yfinance.
    """
    key = _get_apify_key()
    if key:
        items = _run_actor(
            "apify/yahoo-finance-scraper",
            {"symbols": [symbol], "type": "QUOTE"},
            timeout_secs=45,
        )
        if items and len(items) > 0:
            return items[0]

    # Fallback to yfinance
    if YFINANCE_AVAILABLE:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        return {
            "symbol": symbol,
            "price": info.get("regularMarketPrice"),
            "change_pct": info.get("regularMarketChangePercent"),
            "volume": info.get("regularMarketVolume"),
            "market_cap": info.get("marketCap"),
            "pe_ratio": info.get("trailingPE"),
            "iv": info.get("impliedVolatility"),
            "52w_high": info.get("fiftyTwoWeekHigh"),
            "52w_low": info.get("fiftyTwoWeekLow"),
            "source": "yfinance_fallback",
        }
    return {"error": "No data source available", "symbol": symbol}


# ─── Options Chain ────────────────────────────────────────────────────────────

def get_options_chain(symbol: str, expiry: Optional[str] = None) -> dict:
    """
    Full options chain with Greeks. Apify preferred, yfinance fallback.
    """
    key = _get_apify_key()
    if key:
        run_input = {"symbols": [symbol], "type": "OPTIONS"}
        if expiry:
            run_input["expiry"] = expiry
        items = _run_actor("apify/yahoo-finance-scraper", run_input, timeout_secs=60)
        if items and len(items) > 0:
            return {"source": "apify", "data": items}

    # Fallback to yfinance
    if YFINANCE_AVAILABLE:
        ticker = yf.Ticker(symbol)
        expirations = ticker.options
        if not expirations:
            return {"expirations": [], "calls": [], "puts": [], "source": "yfinance_fallback"}
        target = expiry if expiry in expirations else expirations[0]
        chain = ticker.option_chain(target)
        return {
            "expiry": target,
            "all_expirations": list(expirations),
            "calls": chain.calls.to_dict(orient="records") if hasattr(chain, "calls") else [],
            "puts": chain.puts.to_dict(orient="records") if hasattr(chain, "puts") else [],
            "source": "yfinance_fallback",
        }
    return {"error": "No data source available", "symbol": symbol}


# ─── Historical Data ──────────────────────────────────────────────────────────

def get_history(symbol: str, period: str = "1mo", interval: str = "1d") -> list[dict]:
    """
    Historical OHLCV. Apify preferred, yfinance fallback.
    period: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max
    interval: 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo
    """
    key = _get_apify_key()
    if key:
        items = _run_actor(
            "apify/yahoo-finance-scraper",
            {"symbols": [symbol], "type": "HISTORICAL", "period": period, "interval": interval},
            timeout_secs=60,
        )
        if items:
            return items

    # Fallback to yfinance
    if YFINANCE_AVAILABLE:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period, interval=interval)
        if hist.empty:
            return []
        hist.index = hist.index.astype(str)
        records = hist.reset_index().to_dict(orient="records")
        for r in records:
            r["source"] = "yfinance_fallback"
        return records
    return []


# ─── Key Statistics ───────────────────────────────────────────────────────────

def get_key_stats(symbol: str) -> dict:
    """
    Key statistics: beta, short float, institutional ownership, etc.
    Useful for the Shadow's structural weakness analysis.
    """
    key = _get_apify_key()
    if key:
        items = _run_actor(
            "apify/yahoo-finance-scraper",
            {"symbols": [symbol], "type": "KEY_STATISTICS"},
            timeout_secs=45,
        )
        if items and len(items) > 0:
            return items[0]

    # Fallback to yfinance info dict
    if YFINANCE_AVAILABLE:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        return {
            "symbol": symbol,
            "beta": info.get("beta"),
            "short_float": info.get("shortPercentOfFloat"),
            "institutional_ownership": info.get("institutionsPercentHeld"),
            "insider_ownership": info.get("insidersPercentHeld"),
            "forward_pe": info.get("forwardPE"),
            "peg_ratio": info.get("pegRatio"),
            "source": "yfinance_fallback",
        }
    return {"error": "No data source available", "symbol": symbol}


# ─── Status check ─────────────────────────────────────────────────────────────

def get_feed_status() -> dict:
    """Returns which data source is active."""
    return {
        "apify_key_set": bool(_get_apify_key()),
        "yfinance_available": YFINANCE_AVAILABLE,
        "active_source": "apify" if _get_apify_key() else ("yfinance" if YFINANCE_AVAILABLE else "none"),
    }
