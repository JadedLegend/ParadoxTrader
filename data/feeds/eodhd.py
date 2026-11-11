"""
EODHD Data Feed — Paradox Edge Trader v2
=========================================
Env var: EODHD_API_KEY

EODHD (End of Day Historical Data) strengths:
  - End-of-day and intraday historical data for 70+ exchanges globally
  - Fundamental data: P/E, EPS, revenue, balance sheet, cash flow
  - Macro economic indicators (GDP, inflation, interest rates, unemployment)
  - Bonds and treasury yields
  - Options data (end-of-day)
  - Earnings history and calendar
  - Dividends and splits
  - Sentiment data from news and social
  - Economic events calendar

Free tier: 20 API calls/day. Paid tiers start at $19.99/mo.
Docs: https://eodhd.com/financial-apis/
"""

import os
from typing import Optional

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

EODHD_BASE = "https://eodhd.com/api"


def _get_key() -> str:
    key = os.environ.get("EODHD_API_KEY", "").strip()
    return key if key and not key.startswith("YOUR_") else ""


def _get(endpoint: str, params: Optional[dict] = None) -> dict | list:
    if not REQUESTS_AVAILABLE:
        return {"error": "requests not installed"}
    key = _get_key()
    if not key:
        return {"error": "EODHD_API_KEY not set"}
    p = {"api_token": key, "fmt": "json"}
    if params:
        p.update(params)
    try:
        resp = requests.get(f"{EODHD_BASE}{endpoint}", params=p, timeout=20)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


# ─── End-of-Day Price Data ────────────────────────────────────────────────────

def get_eod(symbol: str, exchange: str = "US",
            from_date: Optional[str] = None, to_date: Optional[str] = None,
            period: str = "d") -> list:
    """
    End-of-day OHLCV data.
    exchange: US, LSE, XETRA, etc.
    period: d (daily), w (weekly), m (monthly)
    from_date / to_date: YYYY-MM-DD
    """
    params = {"period": period}
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date
    data = _get(f"/eod/{symbol}.{exchange}", params)
    return data if isinstance(data, list) else []


def get_realtime(symbol: str, exchange: str = "US") -> dict:
    """Real-time (delayed) quote."""
    data = _get(f"/real-time/{symbol}.{exchange}")
    return data if isinstance(data, dict) else {}


# ─── Fundamentals ─────────────────────────────────────────────────────────────

def get_fundamentals(symbol: str, exchange: str = "US") -> dict:
    """
    Full fundamental data: financials, balance sheet, cash flow,
    earnings, valuation ratios, analyst estimates.
    The Alchemist and Oracle's deep research tool.
    """
    return _get(f"/fundamentals/{symbol}.{exchange}")


def get_financials(symbol: str, exchange: str = "US", statement: str = "income_statement") -> dict:
    """
    Specific financial statement.
    statement: income_statement, balance_sheet, cash_flow
    """
    data = get_fundamentals(symbol, exchange)
    if isinstance(data, dict):
        return data.get("Financials", {}).get(statement, {})
    return {}


# ─── Macro Economic Indicators ────────────────────────────────────────────────

def get_macro_indicator(country: str, indicator: str) -> list:
    """
    Macro economic time series data.
    country: USA, GBR, DEU, JPN, CHN, etc.
    indicator examples:
      real_gdp, gdp_growth_rate, inflation_rate, unemployment_rate,
      interest_rate, consumer_price_index, producer_price_index,
      retail_sales, industrial_production, current_account,
      government_debt_to_gdp, federal_funds_rate
    The Oracle's primary macro cycle tool.
    """
    data = _get(f"/macro-indicator/{country}", {"indicator": indicator})
    return data if isinstance(data, list) else []


def get_us_macro_snapshot() -> dict:
    """
    Pull key US macro indicators in one call sequence.
    Uses 4 of the daily quota — call sparingly.
    """
    indicators = {
        "gdp_growth_rate": get_macro_indicator("USA", "real_gdp_growth"),
        "inflation_rate": get_macro_indicator("USA", "inflation_rate"),
        "unemployment_rate": get_macro_indicator("USA", "unemployment_rate"),
        "federal_funds_rate": get_macro_indicator("USA", "federal_funds_rate"),
    }
    # Extract most recent value for each
    snapshot = {}
    for key, series in indicators.items():
        if isinstance(series, list) and series:
            latest = series[-1]
            snapshot[key] = {
                "value": latest.get("value"),
                "date": latest.get("date"),
            }
        else:
            snapshot[key] = {"value": None, "date": None}
    return snapshot


# ─── Treasury Yields & Bonds ──────────────────────────────────────────────────

def get_bond_yield(symbol: str = "US10Y.GBOND") -> list:
    """
    Treasury yield data.
    Common symbols: US10Y.GBOND, US2Y.GBOND, US30Y.GBOND
    The Oracle watches the yield curve for regime signals.
    """
    return get_eod(symbol, exchange="GBOND")


def get_yield_curve_snapshot() -> dict:
    """2yr, 10yr, 30yr yields — the Oracle's yield curve tool."""
    result = {}
    for tenor, sym in [("2yr", "US2Y"), ("10yr", "US10Y"), ("30yr", "US30Y")]:
        data = get_eod(f"{sym}.GBOND", exchange="GBOND")
        if isinstance(data, list) and data:
            result[tenor] = {"yield": data[-1].get("close"), "date": data[-1].get("date")}
        else:
            result[tenor] = {"yield": None, "date": None}
    # Compute 2s10s spread
    try:
        spread = result["10yr"]["yield"] - result["2yr"]["yield"]
        result["2s10s_spread"] = round(spread, 3)
        result["curve_signal"] = "inverted" if spread < 0 else "normal"
    except (TypeError, KeyError):
        result["2s10s_spread"] = None
        result["curve_signal"] = "unknown"
    return result


# ─── Options (EOD) ────────────────────────────────────────────────────────────

def get_options_eod(symbol: str, exchange: str = "US",
                    from_date: Optional[str] = None, to_date: Optional[str] = None) -> dict:
    """End-of-day options data for a symbol."""
    params = {}
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date
    return _get(f"/options/{symbol}.{exchange}", params)


# ─── Earnings ─────────────────────────────────────────────────────────────────

def get_earnings_history(symbol: str, exchange: str = "US", limit: int = 8) -> list:
    """Historical earnings: actual vs estimated EPS and revenue."""
    data = get_fundamentals(symbol, exchange)
    if isinstance(data, dict):
        earnings = data.get("Earnings", {}).get("History", {})
        items = list(earnings.values()) if isinstance(earnings, dict) else []
        return sorted(items, key=lambda x: x.get("date", ""), reverse=True)[:limit]
    return []


# ─── Sentiment ────────────────────────────────────────────────────────────────

def get_sentiment(symbol: str, exchange: str = "US",
                  from_date: Optional[str] = None, to_date: Optional[str] = None) -> list:
    """
    News and social sentiment scores for a symbol.
    Returns daily sentiment: positive/negative/neutral counts and scores.
    """
    params = {}
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date
    data = _get(f"/sentiments", {"s": f"{symbol}.{exchange}", **params})
    return data if isinstance(data, list) else []


# ─── Economic Events Calendar ─────────────────────────────────────────────────

def get_economic_events(from_date: Optional[str] = None,
                        to_date: Optional[str] = None,
                        country: str = "US") -> list:
    """
    Upcoming economic events: Fed meetings, CPI, NFP, GDP releases.
    The Oracle's macro timing tool.
    """
    params = {"country": country}
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date
    data = _get("/economic-events", params)
    return data if isinstance(data, list) else []


# ─── Status ───────────────────────────────────────────────────────────────────

def is_available() -> bool:
    return bool(_get_key())
