"""Frozen OpenRouter readiness and a single-attempt, explicitly armed gateway.

No catalog fetch, credential/environment lookup, default model, tracing, tools,
retry or fallback occurs here. OpenRouter is the application's existing provider
account route, not the Manus built-in proxy. Development uses injected HTTP only.

CLI integration: catalog_snapshot(model_map, public_catalog),
synthetic_catalog_snapshot(model_map), validate_manifest(manifest), and
OpenRouterTransport(explicit_key, http_post=offline_post). The latter is marked
is_live=False when HTTP is injected; real execution requires an explicit live
transport. generate requires the shared store, controller token and stable wake.
"""
from datetime import datetime, timezone
from decimal import Decimal, localcontext
import json
import math
import re
import time
from uuid import uuid4
from threading import Lock

from core.usage.pricing import PricingTable, decimal_text, decimal_value, validate_model
from core.usage.store import UsageStore

AGENT_IDS = ("tempest", "siren", "alchemist", "weaver", "oracle", "shadow", "paradox_hunter")
CAPABILITIES = ("rest", "journal", "inquire", "library", "roam")
LIMIT_CEILINGS = {
    "wakes_per_agent": 2, "max_requests": 28, "max_output_tokens": 1024,
    "max_input_bytes": 24000, "max_runtime_seconds": 900,
    "request_timeout_seconds": 60, "max_parallelism": 3,
}
# Input tokens are conservatively bounded by UTF-8 bytes, not a chars/4 guess.
# This explicit protocol allowance is included in both context and reservation.
PROTOCOL_OVERHEAD_BYTES = 2048
MESSAGE_OVERHEAD_BYTES = 128
_MODEL_FIELDS = {"id", "context_length", "max_completion_tokens", "supported_parameters", "pricing"}
_SAFE_PROVIDER = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._:/+@-]{0,79}\Z")


class ManifestError(ValueError):
    """Readiness failure with a fixed metadata-only message."""


class ProviderError(RuntimeError):
    def __init__(self, code, *, uncertain=False):
        self.code = code
        self.uncertain = uncertain
        super().__init__(code)


def _map(value):
    if not isinstance(value, dict) or set(value) != set(AGENT_IDS):
        raise ManifestError("exact_seven_owner_map_required")
    try:
        return {owner: validate_model(value[owner]) for owner in AGENT_IDS}
    except ValueError:
        raise ManifestError("invalid_model_id") from None


def _rate(value):
    try:
        amount = decimal_value(value)
        if amount > Decimal("1000"):
            raise ValueError
        return decimal_text(amount)
    except ValueError:
        raise ManifestError("invalid_catalog_price") from None


def _positive_int(value, code):
    if type(value) is not int or not 1 <= value <= 100000000:
        raise ManifestError(code)
    return value


def _reject_overrides(row):
    # Provider-specific overrides are not costed by this token/request gateway.
    for key in ("pricing_override", "pricing_overrides", "per_request_limits"):
        if row.get(key) not in (None, {}, []):
            raise ManifestError("unsupported_pricing_override")
    top = row.get("top_provider")
    if isinstance(top, dict):
        for key in ("pricing", "pricing_override", "pricing_overrides"):
            if top.get(key) not in (None, {}, []):
                raise ManifestError("unsupported_pricing_override")


def _model(row, *, api=False):
    if not isinstance(row, dict):
        raise ManifestError("invalid_catalog_model")
    if not api and set(row) != _MODEL_FIELDS:
        raise ManifestError("invalid_snapshot_model_fields")
    _reject_overrides(row)
    try:
        model_id = validate_model(row.get("id"))
    except ValueError:
        raise ManifestError("invalid_model_id") from None
    top = row.get("top_provider")
    maximum = row.get("max_completion_tokens")
    if api and maximum is None and isinstance(top, dict):
        maximum = top.get("max_completion_tokens")
    context = _positive_int(row.get("context_length"), "missing_context_limit")
    if api and isinstance(top, dict):
        if top.get("context_length") is not None:
            context = min(context, _positive_int(top["context_length"], "invalid_provider_context_limit"))
        if top.get("max_completion_tokens") is not None and maximum is not None:
            maximum = min(_positive_int(maximum, "missing_completion_limit"),
                          _positive_int(top["max_completion_tokens"], "invalid_provider_completion_limit"))
    params = row.get("supported_parameters")
    if (not isinstance(params, list) or not params or len(params) > 100
            or any(not isinstance(p, str) or not re.fullmatch(r"[a-z_]{1,80}", p) for p in params)
            or len(set(params)) != len(params) or "max_tokens" not in params):
        raise ManifestError("unsupported_output_cap")
    pricing = row.get("pricing")
    if not isinstance(pricing, dict) or not {"prompt", "completion", "request"} <= pricing.keys():
        raise ManifestError("missing_catalog_price")
    # Unknown units fail closed even when malformed; explicitly zero extra units
    # are safe to omit. Discounts/cache overrides are intentionally unsupported.
    for key, value in pricing.items():
        if key not in ("prompt", "completion", "request") and Decimal(_rate(value)) != 0:
            raise ManifestError("unsupported_billed_unit")
    return {
        "id": model_id,
        "context_length": context,
        "max_completion_tokens": _positive_int(maximum, "missing_completion_limit"),
        "supported_parameters": sorted(params),
        "pricing": {key: _rate(pricing[key]) for key in ("prompt", "completion", "request")},
    }


def catalog_snapshot(model_map, catalog):
    """Normalize *only* selected exact IDs from an explicitly supplied API catalog.

    No network or metadata invention. Extra, unselected models are never frozen.
    Actual availability is only as current as the caller's captured public data.
    """
    selected = set(_map(model_map).values())
    if not isinstance(catalog, dict) or not isinstance(catalog.get("data"), list):
        raise ManifestError("public_api_catalog_required")
    rows = {}
    for row in catalog["data"]:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or row["id"] not in selected:
            continue
        if row["id"] in rows:
            raise ManifestError("duplicate_selected_model")
        rows[row["id"]] = _model(row, api=True)
    if set(rows) != selected:
        raise ManifestError("selected_model_absent")
    return {"source": "synthetic" if catalog.get("synthetic") is True else "openrouter",
            "models": [rows[key] for key in sorted(rows)]}


def synthetic_catalog_snapshot(model_map):
    """Explicit offline-only synthetic metadata; never asserts real availability."""
    selected = sorted(set(_map(model_map).values()))
    return {"source": "synthetic", "models": [{
        "id": model, "context_length": 65536, "max_completion_tokens": 1024,
        "supported_parameters": ["max_tokens"],
        "pricing": {"prompt": "0", "completion": "0", "request": "0"},
    } for model in selected]}


def validate_manifest(manifest):
    """Pure, strict, nonmutating validation; no substitutions or repaired limits."""
    fields = {"schema_version", "mode", "agent_models", "limits", "catalog_snapshot", "capabilities"}
    if not isinstance(manifest, dict) or set(manifest) != fields:
        raise ManifestError("invalid_manifest_fields")
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        raise ManifestError("unsupported_manifest_version")
    mode = manifest["mode"]
    if mode not in ("offline", "real"):
        raise ManifestError("invalid_mode")
    model_map = _map(manifest["agent_models"])
    limits = manifest["limits"]
    if not isinstance(limits, dict) or set(limits) != set(LIMIT_CEILINGS) | {"budget_usd"}:
        raise ManifestError("invalid_limits_fields")
    clean_limits = {}
    for key, ceiling in LIMIT_CEILINGS.items():
        value = limits[key]
        if type(value) is not int or not 1 <= value <= ceiling:
            raise ManifestError("invalid_finite_limit")
        if key == "wakes_per_agent" and value != 2:
            raise ManifestError("two_rounds_required")
        clean_limits[key] = value
    if not isinstance(limits["budget_usd"], str):
        raise ManifestError("budget_decimal_string_required")
    try:
        budget = decimal_value(limits["budget_usd"])
    except ValueError:
        raise ManifestError("invalid_budget") from None
    if mode == "real" and budget <= 0:
        raise ManifestError("positive_real_budget_required")
    clean_limits["budget_usd"] = decimal_text(budget)
    if manifest["capabilities"] != list(CAPABILITIES):
        raise ManifestError("restricted_capabilities_required")
    snapshot = manifest["catalog_snapshot"]
    if (not isinstance(snapshot, dict) or not {"models"} <= snapshot.keys()
            or not snapshot.keys() <= {"models", "source", "captured_at"}
            or not isinstance(snapshot["models"], list)):
        raise ManifestError("invalid_catalog_snapshot")
    source = snapshot.get("source")
    if mode == "offline" and source != "synthetic":
        raise ManifestError("explicit_synthetic_metadata_required")
    if mode == "real" and source not in (None, "openrouter"):
        raise ManifestError("real_catalog_required")
    models = [_model(row) for row in snapshot["models"]]
    selected = set(model_map.values())
    if len(models) != len(selected) or {row["id"] for row in models} != selected:
        raise ManifestError("exact_selected_snapshot_required")
    for row in models:
        if row["max_completion_tokens"] < clean_limits["max_output_tokens"]:
            raise ManifestError("insufficient_output_cap")
        if row["context_length"] < clean_limits["max_input_bytes"] + clean_limits["max_output_tokens"]:
            raise ManifestError("insufficient_context")
    clean_snapshot = {"models": sorted(models, key=lambda row: row["id"])}
    if source is not None:
        clean_snapshot["source"] = source
    if "captured_at" in snapshot:
        captured = snapshot["captured_at"]
        try:
            if not isinstance(captured, str) or len(captured) > 64:
                raise ValueError
            stamp = datetime.fromisoformat(captured.replace("Z", "+00:00"))
            if stamp.utcoffset() is None:
                raise ValueError
        except ValueError:
            raise ManifestError("invalid_catalog_capture_time") from None
        clean_snapshot["captured_at"] = captured
    return {"schema_version": 1, "mode": mode, "agent_models": model_map,
            "limits": clean_limits, "catalog_snapshot": clean_snapshot,
            "capabilities": list(CAPABILITIES)}


def _usage_metadata(data):
    """Equivalent leaf allowlist to llm._usage_metadata, without tracing imports."""
    data = data if isinstance(data, dict) else {}
    usage = data.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    result = {}
    for destination, source in (("input_tokens", "prompt_tokens"), ("output_tokens", "completion_tokens"),
                                ("total_tokens", "total_tokens")):
        value = usage.get(source)
        result[destination] = value if type(value) is int and 0 <= value <= 10000000000 else None
    for destination, source, field, parent in (
        ("cached_input_tokens", "prompt_tokens_details", "cached_tokens", "input_tokens"),
        ("reasoning_tokens", "completion_tokens_details", "reasoning_tokens", "output_tokens"),
    ):
        detail = usage.get(source)
        value = detail.get(field) if isinstance(detail, dict) else None
        result[destination] = value if type(value) is int and 0 <= value <= 10000000000 else None
        if result[destination] is not None and result[parent] is not None and value > result[parent]:
            result[destination] = None
    result["provider_cost_usd"] = None
    if usage.get("cost") is not None:
        try:
            result["provider_cost_usd"] = decimal_text(decimal_value(usage["cost"]))
        except ValueError:
            pass
    result["response_model"] = None
    try:
        result["response_model"] = validate_model(data.get("model"))
    except ValueError:
        pass
    return result


def _provider(data):
    value = data.get("provider") if isinstance(data, dict) else None
    return value if isinstance(value, str) and _SAFE_PROVIDER.fullmatch(value) else None


def _price_number(value, multiplier=1):
    with localcontext() as context:
        context.prec = 180
        exact = Decimal(value) * multiplier
        result = float(exact)
        if not math.isfinite(result):
            raise ManifestError("unrepresentable_price_cap")
        # Never round a routing price ceiling above the frozen admission rate.
        if Decimal.from_float(result) > exact:
            result = math.nextafter(result, 0.0)
        return result


def bounded_input(messages):
    if (not isinstance(messages, list) or not 1 <= len(messages) <= 12
            or any(not isinstance(m, dict) or set(m) != {"role", "content"}
                   or m["role"] not in ("system", "user", "assistant")
                   or not isinstance(m["content"], str) for m in messages)):
        raise ProviderError("invalid_request_messages")
    try:
        encoded = json.dumps(messages, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (UnicodeError, ValueError):
        raise ProviderError("invalid_request_unicode") from None
    return len(encoded) + PROTOCOL_OVERHEAD_BYTES + MESSAGE_OVERHEAD_BYTES * len(messages)


class OpenRouterTransport:
    """One POST, no retries, with reservation before any transport entry.

    http_post has requests.post's signature. Supplying it marks the transport
    offline by default. An explicit is_live=True override is useful for guarded
    real-mode mock tests; the CLI must never infer real authorization from a key.
    """
    def __init__(self, api_key, *, http_post=None, is_live=None):
        if (not isinstance(api_key, str) or not api_key.strip() or len(api_key) > 1024
                or any(ord(c) <= 32 or ord(c) == 127 for c in api_key)):
            raise ProviderError("explicit_api_key_required")
        if http_post is not None and not callable(http_post):
            raise ProviderError("invalid_http_transport")
        if is_live is not None and type(is_live) is not bool:
            raise ProviderError("invalid_transport_mode")
        if http_post is None and is_live is False:
            raise ProviderError("offline_http_injection_required")
        self._api_key = api_key
        self._http_post = http_post
        self.is_live = http_post is None if is_live is None else is_live
        self._ledger_lock = Lock()
        self._ledgers = {}

    def generate(self, *, store, run_id, token, wake_id, agent_id, activity,
                 messages, system_prompt=None, validator=None):
        """Return literal validated content; all operational events are allowlisted.

        A validator can reject strict JSON before a successful request checkpoint.
        Failures never include a header, key, model output or arbitrary exception.
        """
        manifest = validate_manifest(store.get_manifest(run_id))
        if (manifest["mode"] == "offline") == self.is_live:
            raise ProviderError("transport_mode_mismatch")
        if agent_id not in AGENT_IDS or activity not in ("choice", *CAPABILITIES):
            raise ProviderError("invalid_request_owner_or_activity")
        if validator is not None and not callable(validator):
            raise ProviderError("invalid_response_validator")
        full_messages = ([{"role": "system", "content": system_prompt}] if system_prompt else []) + messages
        input_bytes = bounded_input(full_messages)
        limits = manifest["limits"]
        if input_bytes > limits["max_input_bytes"]:
            raise ProviderError("input_bound_exceeded")
        model = manifest["agent_models"][agent_id]
        row = next(row for row in manifest["catalog_snapshot"]["models"] if row["id"] == model)
        pricing = row["pricing"]
        with localcontext() as context:
            context.prec = 180
            reserved = (Decimal(pricing["prompt"]) * input_bytes
                        + Decimal(pricing["completion"]) * limits["max_output_tokens"]
                        + Decimal(pricing["request"]))
        payload = {"model": model, "messages": full_messages,
                   "max_tokens": limits["max_output_tokens"], "stream": False,
                   "provider": {"require_parameters": True, "allow_fallbacks": False,
                                "max_price": {"prompt": _price_number(pricing["prompt"], 1000000),
                                              "completion": _price_number(pricing["completion"], 1000000),
                                              "request": _price_number(pricing["request"])}}}
        post = self._http_post
        if post is None:
            import requests
            post = requests.post
        ledger_path = str(store.safe_run_file(run_id, "usage.sqlite3"))
        with self._ledger_lock:
            if ledger_path not in self._ledgers:
                self._ledgers[ledger_path] = UsageStore(ledger_path, PricingTable())
            usage_store = self._ledgers[ledger_path]
        store.assert_active(run_id, token)
        request_id = store.reserve_request(run_id, wake_id, token, agent_id=agent_id,
                                           activity=activity, model=model, input_bytes=input_bytes,
                                           max_output_tokens=limits["max_output_tokens"],
                                           reserved_usd=decimal_text(reserved))
        event = {"event_id": str(uuid4()), "call_id": request_id, "wake_id": wake_id,
                 "agent_id": agent_id, "activity": activity, "provider": "openrouter",
                 "model": model, "attempt": 1, "created_at": datetime.now(timezone.utc).isoformat(),
                 "http_status": None, "outcome": "transport_error", **_usage_metadata(None)}
        started = time.perf_counter()
        upstream_provider = None
        failure = None
        from .store import RehearsalStopped
        try:
            # This persisted transition is the dispatch linearization point.
            # Stop denies later transitions; already committed transport is
            # in flight and cannot be cancelled by pretending its cost vanished.
            store.mark_dispatched(run_id, request_id, token)
        except RehearsalStopped:
            store.finish_request(run_id, request_id, outcome="not_sent", duration_ms=0,
                                 failure_code="admission_stopped", usage=None)
            raise
        try:
            try:
                response = post("https://openrouter.ai/api/v1/chat/completions",
                                headers={"Authorization": "Bearer " + self._api_key,
                                         "Content-Type": "application/json"},
                                json=payload, timeout=limits["request_timeout_seconds"],
                                allow_redirects=False)
            except Exception:
                raise ProviderError("transport_unconfirmed", uncertain=True) from None
            status = getattr(response, "status_code", None)
            if type(status) is int and 100 <= status <= 599:
                event["http_status"] = status
            event["outcome"] = "http_error" if type(status) is int and not 200 <= status < 300 else "invalid_response"
            try:
                data = response.json()
            except Exception:
                raise ProviderError("invalid_response") from None
            event.update(_usage_metadata(data))
            upstream_provider = _provider(data)
            if type(status) is not int or not 200 <= status < 300:
                raise ProviderError("http_rejected")
            if not isinstance(data, dict) or data.get("error") is not None:
                raise ProviderError("provider_rejected")
            if event["response_model"] is not None and event["response_model"] != model:
                raise ProviderError("returned_model_mismatch")
            choices = data.get("choices")
            if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
                raise ProviderError("invalid_response")
            choice = choices[0]
            if choice.get("finish_reason") != "stop":
                raise ProviderError("output_truncated" if choice.get("finish_reason") == "length" else "unsupported_finish")
            message = choice.get("message")
            content = message.get("content") if isinstance(message, dict) else None
            if (not isinstance(content, str) or len(content) > 12000
                    or (isinstance(message, dict) and message.get("tool_calls"))):
                raise ProviderError("invalid_response")
            try:
                if len(content.encode("utf-8")) > 24000:
                    raise ValueError
                if validator is not None:
                    validator(content)
            except Exception:
                raise ProviderError("invalid_activity_output") from None
            event["outcome"] = "success"
            return content
        except ProviderError as error:
            failure = error
            raise
        finally:
            event["duration_ms"] = max(0, (time.perf_counter() - started) * 1000)
            # Persist ledger before control completion. If a process dies here,
            # recovery remains conservative; never infer missing cost as free.
            try:
                usage_store.record(event)
            except Exception:
                # Accounting failure is not permission to replay a paid request.
                if failure is None:
                    failure = ProviderError("usage_recording_failed", uncertain=True)
            store.finish_request(run_id, request_id,
                                 outcome="uncertain" if failure and failure.uncertain else event["outcome"],
                                 response_model=event["response_model"], provider=upstream_provider,
                                 duration_ms=event["duration_ms"], usage=_usage_metadata(event_to_response(event)),
                                 failure_code=failure.code if failure else None)
            if failure is not None and failure.code == "usage_recording_failed":
                raise failure


def event_to_response(event):
    """Convert the local usage allowlist to OpenRouter shape (no content)."""
    return {"model": event.get("response_model"), "usage": {
        "prompt_tokens": event.get("input_tokens"), "completion_tokens": event.get("output_tokens"),
        "total_tokens": event.get("total_tokens"), "cost": event.get("provider_cost_usd"),
        "prompt_tokens_details": {"cached_tokens": event.get("cached_input_tokens")},
        "completion_tokens_details": {"reasoning_tokens": event.get("reasoning_tokens")},
    }}
