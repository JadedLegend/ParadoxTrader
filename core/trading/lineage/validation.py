"""Strict local metadata validation. No real contract lookup or model journal import."""
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from .errors import LineageError

STRUCTURE_FIELDS = frozenset({"symbol", "underlying", "expiry", "option_type", "strike",
                             "side", "intent", "qty", "order_type", "limit_price", "multiplier"})


def text(value, name, *, maximum=20000, empty=True):
    if not isinstance(value, str) or len(value) > maximum or (not empty and not value.strip()):
        raise LineageError(f"{name} must be an explicit {'nonempty ' if not empty else ''}string")
    return value


def integer(value, name, *, minimum=1, maximum=1000000):
    if type(value) is not int or not minimum <= value <= maximum:
        raise LineageError(f"{name} must be a whole integer from {minimum} to {maximum}")
    return value


def decimal_string(value, name, *, positive=True):
    if not isinstance(value, str) or len(value) > 100:
        raise LineageError(f"{name} must be a finite decimal string")
    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", value):
        raise LineageError(f"{name} must be a finite decimal string")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise LineageError(f"invalid {name}") from exc
    if not number.is_finite() or (positive and number <= 0):
        raise LineageError(f"{name} must be positive and finite")
    # format, not normalize(), avoids context rounding while canonicalizing.
    result = format(number, "f")
    if "." in result:
        result = result.rstrip("0").rstrip(".")
    return "0" if number == 0 else result


def execution_price(value, name):
    """Supported local USD/share price: positive, <=1e6, <=8 decimal places."""
    canonical = decimal_string(value, name)
    scale = len(canonical.split(".", 1)[1]) if "." in canonical else 0
    if Decimal(canonical) > Decimal("1000000") or scale > 8:
        raise LineageError(f"{name} exceeds supported mock price magnitude or precision")
    return canonical


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def validate_structure(structure):
    if not isinstance(structure, dict) or set(structure) != STRUCTURE_FIELDS:
        raise LineageError("structure must contain only the explicit single-leg contract fields")
    result = dict(structure)
    symbol = text(result["symbol"], "symbol", maximum=21, empty=False)
    underlying = text(result["underlying"], "underlying", maximum=6, empty=False)
    expiry = text(result["expiry"], "expiry", maximum=10, empty=False)
    try:
        expiry_date = date.fromisoformat(expiry)
    except ValueError as exc:
        raise LineageError("expiry must be an ISO date") from exc
    match = re.fullmatch(r"([A-Z][A-Z0-9]{0,5})(\d{6})([CP])(\d{8})", symbol)
    if not match or result["option_type"] not in ("call", "put"):
        raise LineageError("invalid OCC option symbol/type")
    result["strike"] = decimal_string(result["strike"], "strike")
    result["limit_price"] = execution_price(result["limit_price"], "limit_price")
    if (match[1] != underlying or match[2] != expiry_date.strftime("%y%m%d")
            or match[3] != ("C" if result["option_type"] == "call" else "P")
            or Decimal(match[4]) / Decimal(1000) != Decimal(result["strike"])):
        raise LineageError("OCC symbol and contract metadata do not match")
    integer(result["qty"], "qty")
    if type(result["multiplier"]) is not int or result["multiplier"] != 100:
        raise LineageError("only multiplier 100 is supported")
    if result["order_type"] != "limit":
        raise LineageError("only limit orders are supported")
    if (result["side"], result["intent"]) not in (("buy", "open"), ("sell", "close")):
        raise LineageError("only long opening buys and closing sells are supported")
    return result
