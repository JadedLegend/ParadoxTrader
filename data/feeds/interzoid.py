"""
Interzoid Data Feed — Paradox Edge Trader v2
=============================================
Env var: INTERZOID_API_KEY

Interzoid provides data enrichment and financial intelligence APIs.
Primary use cases for this system:
  - Company information lookup and enrichment
  - Stock ticker to company name/sector resolution
  - Financial data enrichment for context building

Docs: https://www.interzoid.com/apis
"""

import os
from typing import Optional

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

INTERZOID_BASE = "https://api.interzoid.com"


def _get_key() -> str:
    key = os.environ.get("INTERZOID_API_KEY", "").strip()
    return key if key and not key.startswith("YOUR_") else ""


def _get(endpoint: str, params: Optional[dict] = None) -> dict:
    if not REQUESTS_AVAILABLE:
        return {"error": "requests not installed"}
    key = _get_key()
    if not key:
        return {"error": "INTERZOID_API_KEY not set"}
    p = {"license": key}
    if params:
        p.update(params)
    try:
        resp = requests.get(f"{INTERZOID_BASE}{endpoint}", params=p, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


# ─── Stock / Company Lookup ───────────────────────────────────────────────────

def get_stock_info(ticker: str) -> dict:
    """
    Look up company information by stock ticker symbol.
    Returns company name, exchange, sector, and other metadata.
    """
    return _get("/getstock", {"ticker": ticker})


def get_company_info(company_name: str) -> dict:
    """
    Look up company information by company name.
    Useful for enriching news mentions with structured data.
    """
    return _get("/getcompanyinfo", {"company": company_name})


# ─── Currency & Rates ─────────────────────────────────────────────────────────

def get_currency_rate(currency: str) -> dict:
    """
    Current exchange rate for a currency pair vs USD.
    currency: EUR, GBP, JPY, CNY, etc.
    The Weaver uses this for cross-asset correlation analysis.
    """
    return _get("/getcurrencyrate", {"currency": currency})


def get_major_currency_rates() -> dict:
    """
    Pull major currency rates vs USD in one call sequence.
    Returns EUR, GBP, JPY, CNY, CAD rates.
    """
    rates = {}
    for currency in ["EUR", "GBP", "JPY", "CNY", "CAD", "AUD", "CHF"]:
        result = get_currency_rate(currency)
        if "error" not in result:
            rates[currency] = {
                "rate": result.get("Rate") or result.get("rate"),
                "raw": result,
            }
        else:
            rates[currency] = {"rate": None, "error": result.get("error")}
    return rates


# ─── Global Market Intelligence ───────────────────────────────────────────────

def get_global_time(timezone: str) -> dict:
    """
    Current time in any timezone — useful for tracking global market hours.
    timezone: America/New_York, Europe/London, Asia/Tokyo, etc.
    """
    return _get("/gettime", {"timezone": timezone})


def get_market_hours_status() -> dict:
    """
    Check which major global markets are currently open.
    The Weaver uses this for cross-market correlation timing.
    """
    markets = {
        "NYSE": "America/New_York",
        "LSE": "Europe/London",
        "TSE": "Asia/Tokyo",
        "SSE": "Asia/Shanghai",
        "ASX": "Australia/Sydney",
    }
    status = {}
    for market, tz in markets.items():
        result = get_global_time(tz)
        if "error" not in result:
            status[market] = {
                "timezone": tz,
                "current_time": result.get("CurrentTime") or result.get("currenttime"),
                "raw": result,
            }
    return status


# ─── Status ───────────────────────────────────────────────────────────────────

def is_available() -> bool:
    return bool(_get_key())
