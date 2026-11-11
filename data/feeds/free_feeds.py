"""
Free Financial Data Feeds — Paradox Edge Trader v2
====================================================
No-key-required data sources:
  - Yahoo Finance (via yfinance)
  - FRED (Federal Reserve Economic Data) — free key
  - Fear & Greed Index (CNN)
  - VIX data
  - Options flow proxies

These supplement FMP and provide redundancy.
"""

from typing import Optional

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


# ─── Yahoo Finance ────────────────────────────────────────────────────────────

def get_yf_quote(symbol: str) -> dict:
    if not YFINANCE_AVAILABLE:
        return {"error": "yfinance not installed. Run: pip install yfinance"}
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
    }


def get_yf_options(symbol: str, expiry: Optional[str] = None) -> dict:
    if not YFINANCE_AVAILABLE:
        return {"error": "yfinance not installed"}
    ticker = yf.Ticker(symbol)
    expirations = ticker.options
    if not expirations:
        return {"expirations": [], "calls": [], "puts": []}
    target = expiry if expiry in expirations else expirations[0]
    chain = ticker.option_chain(target)
    return {
        "expiry": target,
        "all_expirations": list(expirations),
        "calls": chain.calls.to_dict(orient="records") if hasattr(chain, "calls") else [],
        "puts": chain.puts.to_dict(orient="records") if hasattr(chain, "puts") else [],
    }


def get_yf_history(symbol: str, period: str = "1mo", interval: str = "1d") -> list[dict]:
    if not YFINANCE_AVAILABLE:
        return []
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period=period, interval=interval)
    if hist.empty:
        return []
    hist.index = hist.index.astype(str)
    return hist.reset_index().to_dict(orient="records")


def get_vix() -> dict:
    return get_yf_quote("^VIX")


def get_spy_data() -> dict:
    return get_yf_quote("SPY")


# ─── Fear & Greed Index ───────────────────────────────────────────────────────

def get_fear_greed() -> dict:
    """CNN Fear & Greed Index via their unofficial API."""
    if not REQUESTS_AVAILABLE:
        return {"error": "requests not installed"}
    try:
        resp = requests.get(
            "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        fg = data.get("fear_and_greed", {})
        return {
            "score": fg.get("score"),
            "rating": fg.get("rating"),
            "timestamp": fg.get("timestamp"),
        }
    except Exception as e:
        return {"error": str(e)}


# ─── FRED Economic Data ───────────────────────────────────────────────────────

def get_fred_series(series_id: str, api_key: Optional[str] = None, limit: int = 10) -> list[dict]:
    """
    Fetch a FRED data series. Free key available at fred.stlouisfed.org.
    Common series: FEDFUNDS, CPIAUCSL, UNRATE, GDP, DGS10 (10yr Treasury)
    """
    if not REQUESTS_AVAILABLE:
        return []
    import os
    key = api_key or os.environ.get("FRED_API_KEY", "")
    if not key:
        return [{"error": "FRED_API_KEY not set. Get a free key at fred.stlouisfed.org"}]
    try:
        resp = requests.get(
            "https://api.stlouisfed.org/fred/series/observations",
            params={
                "series_id": series_id,
                "api_key": key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": limit,
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("observations", [])
    except Exception as e:
        return [{"error": str(e)}]


# ─── Composite Market Snapshot ────────────────────────────────────────────────

def get_market_snapshot() -> dict:
    """
    Quick composite snapshot: VIX, SPY, Fear & Greed.
    Used by agents during 'monitor' action.
    """
    vix = get_vix()
    spy = get_spy_data()
    fg = get_fear_greed()

    return {
        "vix": vix.get("price"),
        "vix_change_pct": vix.get("change_pct"),
        "spy_price": spy.get("price"),
        "spy_change_pct": spy.get("change_pct"),
        "fear_greed_score": fg.get("score"),
        "fear_greed_rating": fg.get("rating"),
        "market_mood": _classify_mood(vix.get("price"), fg.get("score")),
    }


def _classify_mood(vix: Optional[float], fg_score: Optional[float]) -> str:
    if vix is None:
        return "unknown"
    if vix > 30:
        return "fear_regime"
    if vix > 20:
        return "elevated_tension"
    if fg_score is not None and fg_score > 75:
        return "greed_regime"
    if fg_score is not None and fg_score < 25:
        return "extreme_fear"
    return "neutral"
