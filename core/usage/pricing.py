"""Optional, explicit local token rates; never fetch prices or read system.yaml.

Cost precedence is provider-reported USD (including zero), then token estimate,
then unknown. Estimate = ((input - cached) * input_rate + cached * cache_rate
+ output * output_rate) / 1,000,000. Reasoning tokens are a subset of output
and are NEVER added. A known zero cache count allows ordinary input pricing;
a positive cache count needs a cache rate, and an absent cache count remains
unknown rather than silently assuming zero. Estimates cover token charges
ONLY, not per-request fees, subscriptions, infrastructure or invoices.

A snapshot contains only the explicitly allowed rate fields and is persisted
at write time. Historical records are never repriced on reads.
"""

from datetime import date
from decimal import Decimal, InvalidOperation, localcontext
import json
from pathlib import Path
import re

_PROVIDERS = frozenset({"openrouter", "perplexity"})
_MODEL = re.compile(r"[a-zA-Z0-9_.:/+@-]{1,128}\Z")
_SOURCE = re.compile(r"[a-zA-Z0-9_. ()-]{1,160}\Z")
_DECIMAL = re.compile(r"[+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\Z")


def decimal_value(value, field: str = "decimal") -> Decimal:
    """Accept bounded nonnegative finite decimals, never booleans.

    At most 256 text characters, 64 significant digits, and exponents/adjusted
    magnitude in [-100, 100] keep untrusted local JSON arithmetic bounded.
    """
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError(f"invalid {field}")
    try:
        text = str(value)
        if len(text) > 256 or not _DECIMAL.fullmatch(text):
            raise ValueError()
        result = Decimal(text)
    except (InvalidOperation, ValueError, OverflowError):
        raise ValueError(f"invalid {field}") from None
    if not result.is_finite() or result < 0:
        raise ValueError(f"invalid {field}")
    digits = result.as_tuple().digits
    significant_digits = len(digits)
    while significant_digits > 1 and digits[significant_digits - 1] == 0:
        significant_digits -= 1
    if (significant_digits > 64 or not -100 <= result.as_tuple().exponent <= 100
            or not -100 <= result.adjusted() <= 100):
        raise ValueError(f"invalid {field}")
    return result


def decimal_text(value: Decimal) -> str:
    """Canonical exact decimal text, retaining very small/large exponents."""
    if value == 0:
        return "0"
    with localcontext() as ctx:
        ctx.prec = max(28, len(value.as_tuple().digits))
        normalized = value.normalize()
    # normalize() turns whole numbers with trailing zeros into exponents
    # (10 -> "1E+1"); write those as plain integers. Tiny fractions keep
    # their exponent form, as before.
    if normalized.as_tuple().exponent > 0 and normalized.adjusted() < 28:
        return format(normalized, "f")
    return str(normalized)


def decimal_add(left: Decimal, right: Decimal) -> Decimal:
    """Exact addition independent of the process-wide Decimal context."""
    with localcontext() as ctx:
        low = min(left.as_tuple().exponent, right.as_tuple().exponent)
        ctx.prec = max(28, max(left.adjusted(), right.adjusted()) - low + 3)
        return left + right


def validate_provider(value) -> str:
    if not isinstance(value, str) or value not in _PROVIDERS:
        raise ValueError("invalid provider")
    return value


def validate_model(value) -> str:
    if not isinstance(value, str) or not _MODEL.fullmatch(value):
        raise ValueError("invalid model")
    return value


class PricingTable:
    """A validated snapshot of operator-supplied rates (empty by default).

    Direct construction/from_file rejects malformed data. The optional default
    loader converts unreadable/malformed files to invalid_pricing coverage so
    the request event can still be recorded without inventing a cost.
    """

    def __init__(self, data: dict | None = None):
        self._rates: dict[tuple[str, str], dict] = {}
        self.invalid = False
        if data is None:
            data = {"schema_version": 1, "rates": []}
        if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data["schema_version"] != 1:
            raise ValueError("invalid pricing schema_version")
        rates = data.get("rates")
        if not isinstance(rates, list) or len(rates) > 1000:
            raise ValueError("invalid pricing rates")
        for raw in rates:
            if not isinstance(raw, dict):
                raise ValueError("invalid pricing rate")
            provider = validate_provider(raw.get("provider"))
            model = validate_model(raw.get("model"))
            source = raw.get("source")
            as_of = raw.get("as_of")
            if not isinstance(source, str) or not _SOURCE.fullmatch(source):
                raise ValueError("invalid pricing source")
            if re.search(r"(?i)^(?:bearer|basic)\s|(?:sk|pplx)-[a-zA-Z0-9]", source):
                raise ValueError("invalid pricing source")
            if not isinstance(as_of, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", as_of):
                raise ValueError("invalid pricing as_of")
            try:
                date.fromisoformat(as_of)
            except ValueError:
                raise ValueError("invalid pricing as_of") from None
            snapshot = {"schema_version": 1, "provider": provider, "model": model,
                        "source": source, "as_of": as_of}
            for key in ("input_usd_per_million", "output_usd_per_million"):
                snapshot[key] = decimal_text(decimal_value(raw.get(key), key))
            cached = raw.get("cached_input_usd_per_million")
            snapshot["cached_input_usd_per_million"] = (
                None if cached is None else decimal_text(decimal_value(cached, "cached rate"))
            )
            if (provider, model) in self._rates:
                raise ValueError("duplicate pricing rate")
            self._rates[provider, model] = snapshot

    @classmethod
    def from_file(cls, path: str | Path) -> "PricingTable":
        path = Path(path)
        if path.stat().st_size > 1_048_576:
            raise ValueError("pricing file too large")
        try:
            # parse_float retains every digit from operator JSON numbers.
            return cls(json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal))
        except (OSError, UnicodeError, json.JSONDecodeError):
            raise ValueError("invalid pricing file") from None

    @classmethod
    def invalid_table(cls) -> "PricingTable":
        table = cls()
        table.invalid = True
        return table

    def resolve(self, event: dict) -> dict:
        """Resolve a validated event to cost fields safe for persistence."""
        result = {"cost_usd": None, "cost_status": "unknown", "cost_scope": None,
                  "cost_reason": None, "pricing_snapshot": None}
        if event.get("provider_cost_usd") is not None:
            result.update(cost_usd=decimal_text(decimal_value(event["provider_cost_usd"])),
                          cost_status="reported", cost_scope="provider_reported")
            return result
        input_tokens, output_tokens = event.get("input_tokens"), event.get("output_tokens")
        if input_tokens is None or output_tokens is None:
            result["cost_reason"] = "missing_usage"
            return result
        if self.invalid:
            result["cost_reason"] = "invalid_pricing"
            return result
        # An explicit returned model is authoritative for token-rate matching;
        # never apply a requested alias/model's possibly different price.
        billing_model = event.get("response_model") or event["model"]
        rate = self._rates.get((event["provider"], billing_model))
        if rate is None:
            result["cost_reason"] = "missing_rates"
            return result
        cached = event.get("cached_input_tokens")
        if cached is None or (cached > 0 and rate["cached_input_usd_per_million"] is None):
            result["cost_reason"] = "unknown_cache_usage"
            return result
        # Counts are validated by the ledger. Do not double-add total/reasoning.
        rates = [Decimal(rate["input_usd_per_million"]), Decimal(rate["output_usd_per_million"])]
        cache_rate = Decimal(rate["cached_input_usd_per_million"] or "0")
        with localcontext() as ctx:
            all_rates = rates + [cache_rate]
            low = min(r.as_tuple().exponent for r in all_rates)
            ctx.prec = max(40, max(r.adjusted() for r in all_rates) - low + 24)
            amount = ((input_tokens - cached) * rates[0] + cached * cache_rate
                      + output_tokens * rates[1]) / Decimal(1_000_000)
        result.update(cost_usd=decimal_text(amount), cost_status="estimated",
                      cost_scope="token_only", pricing_snapshot=dict(rate))
        return result


def get_default_pricing() -> PricingTable:
    """Load only config/usage_pricing.json, else DATA_DIR/usage_pricing.json.

    An explicit root file takes precedence (even if invalid). Missing optional
    files mean an empty table. This function is called only on explicit use;
    importing this module performs no I/O and reads no API credentials.
    """
    root_file = Path(__file__).resolve().parents[2] / "config" / "usage_pricing.json"
    try:
        if root_file.exists():
            return PricingTable.from_file(root_file)
        from core.data_dir import DATA_DIR
        data_file = DATA_DIR / "usage_pricing.json"
        if data_file.exists():
            return PricingTable.from_file(data_file)
        return PricingTable()
    except (OSError, ValueError, TypeError, OverflowError):
        return PricingTable.invalid_table()
