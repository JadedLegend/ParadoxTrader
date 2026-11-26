"""Explicit, private finite rehearsal state. Importing/reading never prepares a run.

The control database has immutable manifest/jobs, write-once private choice and
output checkpoints, and a metadata-only admission ledger. A controller token is
not an expiring lease: only explicit operator recovery can revoke it. Admission
reservations remain charged even when the result is unknown (or fails).
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, localcontext
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
import time
from uuid import UUID, uuid4

from core.usage.pricing import (decimal_add as _decimal_add, decimal_text as _decimal_text,
                                decimal_value, validate_model)

from .calls import CALL_FIELDS, CALL_OPTIONS, validate_call_fields
from .notebook import validate_line

AGENT_IDS = OWNERS = (
    "tempest", "siren", "alchemist", "weaver", "oracle", "shadow", "paradox_hunter",
)
CAPABILITIES = ("rest", "journal", "inquire", "library", "roam")
# A call (docs/specs/CALLS_AND_SETTLEMENT.md) is offered beside the five, only on
# wakes with a market window, so it is a valid choice but not one of the frozen offers.
CHOICE_ACTIONS = (*CAPABILITIES, "call", "skill", "compost_notebook")  # skill: open one shelf skill
# (SKILL_SHELF.md); compost_notebook: move the notebook into one journal compost note (NOTEBOOK.md).
# The library's rooms (docs/specs/LIBRARY_ROOMS.md). A library choice may name one.
LIBRARY_ROOMS = ("writings", "research")

JOURNAL_OPTIONS = {
    "modes": ["note", "compost", "distill", "witness"],
    "channels": ["trading", "idea", "orientation", "unclassified"],
    "default_channels": ["unclassified"], "max_channels": 3,
    "source_ids_only": "distill", "max_source_ids": 20,
    "release_only": "distill", "release_type": "boolean",
    "witness_prior_owner_limit": 3, "distillation_is_optional": True,
}
DEFAULT_LIMITS = {
    "wakes_per_agent": 2, "max_requests": 28, "max_output_tokens": 1024,
    "max_input_bytes": 24000, "max_runtime_seconds": 900,
    "request_timeout_seconds": 60, "max_parallelism": 3,
}
# A "day" run (one continuing day in the agents' home) adds each agent's wakes
# as they happen, up to MAX_WAKES_PER_AGENT, instead of a fixed two rounds.
MAX_WAKES_PER_AGENT = 120
DAY_MAX_OUTPUT_TOKENS = 3000  # Day runs only; full rehearsals keep DEFAULT_LIMITS.
DAY_MAX_INPUT_BYTES = 48000  # Day runs only, as above; matches provider.DAY_MAX_INPUT_BYTES.
# The frozen page also stores structured market evidence for sealing and replay.
MAX_PRIVATE_CONTEXT_CHARS = DAY_MAX_INPUT_BYTES + 16000
LIMIT_CAPS = {**DEFAULT_LIMITS, "wakes_per_agent": MAX_WAKES_PER_AGENT,
              "max_requests": 2 * MAX_WAKES_PER_AGENT * 7, "max_output_tokens": DAY_MAX_OUTPUT_TOKENS,
              "max_input_bytes": DAY_MAX_INPUT_BYTES}
# The witness snapshot holds a whole run: every owner's rounds and every request.
# These match the bounds core.runtime.rehearsal.witness checks a snapshot against.
WITNESS_MAX_JOBS = len(OWNERS) * MAX_WAKES_PER_AGENT
RUN_KINDS = ("rehearsal", "day")
_SAFE = re.compile(r"[a-zA-Z0-9_.:-]{1,128}\Z")
_LABEL = re.compile(r"[a-zA-Z0-9_.:/+@ -]{1,128}\Z")
_TERMINAL = frozenset({"completed", "failed", "stopped", "uncertain"})
_OUTCOMES = frozenset({"success", "http_error", "transport_error", "invalid_response", "failed", "uncertain", "not_sent"})
_TOKEN_FIELDS = ("input_tokens", "output_tokens", "cached_input_tokens", "reasoning_tokens", "total_tokens")
_FINISH_REASONS = frozenset({"stop", "length", "tool_calls", "content_filter", "unknown"})
# Keep the provider's conservative bounded_input accounting without importing it.
_INPUT_PROTOCOL_BYTES, _INPUT_MESSAGE_BYTES = 2048, 128
_RUN_FILES = frozenset({
    "control.sqlite3", "usage.sqlite3", "trade_queue.sqlite3", "calls.sqlite3", "notebook.sqlite3",
    "library.sqlite3",
    "witness.sqlite3", "library_corpus.json", "library_research_corpus.json", "library_research.sqlite3",
    "profiles/snapshot.json", "home.json",
    *(f"profiles/{owner}_{kind}.json" for owner in OWNERS for kind in ("soul", "living")),
    *(f"memory/{owner}.sqlite3" for owner in OWNERS),
    *(f"memory/{owner}-{owner}-r{round_number}-library.json" for owner in OWNERS
      for round_number in range(1, MAX_WAKES_PER_AGENT + 1)),
})


class RehearsalError(ValueError):
    """Bounded safe error, with no provider content or credentials."""


class RehearsalConflict(RehearsalError):
    pass


class RehearsalStopped(RehearsalError):
    pass


class RehearsalBudgetExceeded(RehearsalError):
    pass


def decimal_add(left, right):
    # Reuse exact bounded helpers, but do not inherit a caller's tiny exponent
    # range. Valid leaf decimals have magnitude/exponent in [-100, 100].
    with localcontext() as context:
        context.Emax, context.Emin, context.clamp = 999, -999, 0
        return _decimal_add(left, right)


def decimal_text(value):
    with localcontext() as context:
        context.Emax, context.Emin, context.clamp = 999, -999, 0
        return _decimal_text(value)


def _integer(value, field, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise RehearsalError(f"invalid {field}")
    return value


def _safe(value, field, *, nullable=False, label=False):
    if nullable and value is None:
        return None
    if not isinstance(value, str) or not (_LABEL if label else _SAFE).fullmatch(value):
        raise RehearsalError(f"invalid {field}")
    return value


def _money(value, field):
    try:
        return decimal_value(value, field)
    except (ValueError, OverflowError):
        raise RehearsalError(f"invalid {field}") from None


def _model(value):
    try:
        return validate_model(value)
    except ValueError:
        raise RehearsalError("invalid model") from None


def _uuid(value, field="run_id"):
    if not isinstance(value, str) or len(value) != 36:
        raise RehearsalError(f"invalid {field}")
    try:
        if str(UUID(value)) != value:
            raise ValueError()
    except ValueError:
        raise RehearsalError(f"invalid {field}") from None
    return value


def _dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _bounded_json(value, field, cap):
    def strict(item, depth=0):
        if depth > 32:
            raise ValueError()
        if type(item) is dict:
            if any(type(key) is not str for key in item):
                raise ValueError()
            for child in item.values():
                strict(child, depth + 1)
        elif type(item) is list:
            for child in item:
                strict(child, depth + 1)
        elif type(item) not in (str, int, float, bool, type(None)):
            raise ValueError()
    try:
        strict(value)
        serialized = _dump(value)
        serialized.encode("utf-8")
    except (UnicodeError, ValueError, TypeError, RecursionError):
        raise RehearsalError(f"invalid {field}") from None
    if len(serialized) > cap:
        raise RehearsalError(f"invalid {field}")
    return serialized


def _message_input(messages):
    if not isinstance(messages, list) or not 1 <= len(messages) <= 12:
        raise RehearsalError("invalid request messages")
    normalized = []
    for message in messages:
        if (not isinstance(message, dict) or set(message) != {"role", "content"}
                or not isinstance(message["role"], str)
                or message["role"] not in ("system", "user", "assistant")
                or not isinstance(message["content"], str)
                or len(message["content"]) > DAY_MAX_INPUT_BYTES):
            raise RehearsalError("invalid request messages")
        normalized.append({"role": message["role"], "content": message["content"]})
    try:
        literal = _dump(normalized)
        encoded = literal.encode("utf-8")
    except (UnicodeError, ValueError, TypeError):
        raise RehearsalError("invalid request messages") from None
    size = len(encoded) + _INPUT_PROTOCOL_BYTES + _INPUT_MESSAGE_BYTES * len(normalized)
    if size > DAY_MAX_INPUT_BYTES:  # Each run's own, smaller limit is checked on admission.
        raise RehearsalBudgetExceeded("request input limit exceeded")
    return literal, hashlib.sha256(encoded).hexdigest(), size


def _decision_metadata(value):
    keys = {"schema_version", "offered_actions", "action_costs", "constraints",
            "admission_snapshot", "model", "continuity"}
    if not isinstance(value, dict) or not keys <= set(value) or set(value) - keys - {"journal_options", "call_options"}:
        raise RehearsalError("invalid decision metadata")
    if "call_options" in value and _dump(value["call_options"]) != _dump(CALL_OPTIONS):
        raise RehearsalError("invalid call options")
    if "journal_options" in value and _dump(value["journal_options"]) != _dump(JOURNAL_OPTIONS):
        raise RehearsalError("invalid journal options")
    _integer(value["schema_version"], "schema_version", 1, 1)
    if value["offered_actions"] != list(CAPABILITIES):
        raise RehearsalError("invalid offered_actions")
    costs = value["action_costs"]
    if not isinstance(costs, list) or not 1 <= len(costs) <= len(CAPABILITIES):
        raise RehearsalError("invalid action_costs")
    seen = set()
    for cost in costs:
        if (not isinstance(cost, dict)
                or set(cost) != {"action", "max_requests", "reservation_ceiling_usd", "basis"}
                or not isinstance(cost["action"], str) or cost["action"] not in CAPABILITIES
                or cost["action"] in seen or cost["basis"] != "catalog_upper_bound"):
            raise RehearsalError("invalid action_costs")
        seen.add(cost["action"])
        maximum = 1 if cost["action"] == "rest" else 2
        _integer(cost["max_requests"], "action max_requests", maximum, maximum)
        if not isinstance(cost["reservation_ceiling_usd"], str):
            raise RehearsalError("invalid reservation_ceiling_usd")
        _money(cost["reservation_ceiling_usd"], "reservation_ceiling_usd")
    limits = value["constraints"]
    if not isinstance(limits, dict) or set(limits) != set(DEFAULT_LIMITS) | {"budget_usd"}:
        raise RehearsalError("invalid constraints")
    for name, cap in LIMIT_CAPS.items():
        _integer(limits[name], name, 1, cap)
    if not isinstance(limits["budget_usd"], str):
        raise RehearsalError("invalid budget_usd")
    _money(limits["budget_usd"], "budget_usd")
    snapshot = value["admission_snapshot"]
    if (not isinstance(snapshot, dict) or set(snapshot) != {"reserved_usd", "remaining_budget_usd",
            "request_count", "remaining_requests", "is_reservation"}
            or snapshot["is_reservation"] is not False):
        raise RehearsalError("invalid admission_snapshot")
    for name in ("reserved_usd", "remaining_budget_usd"):
        if not isinstance(snapshot[name], str):
            raise RehearsalError("invalid admission_snapshot")
        _money(snapshot[name], name)
    _integer(snapshot["request_count"], "request_count", 0, LIMIT_CAPS["max_requests"])
    _integer(snapshot["remaining_requests"], "remaining_requests", 0, LIMIT_CAPS["max_requests"])
    model = value["model"]
    if (not isinstance(model, dict) or set(model) != {"requested_model", "context_length",
            "max_completion_tokens", "catalog_source"}
            or model["catalog_source"] not in (None, "synthetic", "openrouter")):
        raise RehearsalError("invalid decision model")
    _model(model["requested_model"])
    for name in ("context_length", "max_completion_tokens"):
        _integer(model[name], name, 1, 100_000_000)
    continuity = value["continuity"]
    if (not isinstance(continuity, dict) or set(continuity) != {"status", "refs", "truncated", "chars"}
            or not isinstance(continuity["status"], str)
            or continuity["status"] not in ("empty", "available", "included", "unavailable", "truncated")
            or type(continuity["truncated"]) is not bool):
        raise RehearsalError("invalid continuity")
    _integer(continuity["chars"], "continuity chars", 0, 8000)
    refs = continuity["refs"]
    if not isinstance(refs, list) or len(refs) > 128:
        raise RehearsalError("invalid continuity refs")
    for ref in refs:
        if (not isinstance(ref, dict) or not {"kind", "id"} <= set(ref)
                or set(ref) - {"kind", "id", "wake_id", "agent_id"}):
            raise RehearsalError("invalid continuity ref")
        _refs([{"kind": ref["kind"], "id": ref["id"]}])
        if "wake_id" in ref:
            _safe(ref["wake_id"], "source wake_id")
        if "agent_id" in ref and ref["agent_id"] not in OWNERS:
            raise RehearsalError("invalid source owner")
    return _bounded_json(value, "decision metadata", 16000)


def _validate_manifest(raw):
    """Local pure validation; no provider/network/scheduler import is needed.

    The provider may perform additional real-catalog readiness validation before
    prepare. This store independently enforces all persisted finite bounds.
    """
    keys = {"schema_version", "mode", "agent_models", "limits", "catalog_snapshot", "capabilities"}
    if (not isinstance(raw, dict) or set(raw) - {"kind"} != keys
            or type(raw.get("schema_version")) is not int or raw["schema_version"] != 1):
        raise RehearsalError("invalid manifest")
    kind = raw.get("kind", "rehearsal")
    if kind not in RUN_KINDS:
        raise RehearsalError("invalid run kind")
    if raw["mode"] not in ("offline", "real"):
        raise RehearsalError("invalid mode")
    models = raw["agent_models"]
    if not isinstance(models, dict) or set(models) != set(OWNERS):
        raise RehearsalError("invalid agent_models")
    models = {owner: _model(models[owner]) for owner in OWNERS}
    limits = raw["limits"]
    if not isinstance(limits, dict) or set(limits) != set(DEFAULT_LIMITS) | {"budget_usd"}:
        raise RehearsalError("invalid limits")
    limits = {name: _integer(limits[name], name, 1, cap) for name, cap in LIMIT_CAPS.items()} | {"budget_usd": raw["limits"]["budget_usd"]}
    if kind == "rehearsal" and (limits["wakes_per_agent"] != 2
                                or limits["max_requests"] > DEFAULT_LIMITS["max_requests"]
                                or limits["max_output_tokens"] > DEFAULT_LIMITS["max_output_tokens"]
                                or limits["max_input_bytes"] > DEFAULT_LIMITS["max_input_bytes"]):
        raise RehearsalError("two rounds required")
    if not isinstance(limits["budget_usd"], str):
        raise RehearsalError("invalid budget_usd")
    budget = _money(limits["budget_usd"], "budget_usd")
    if raw["mode"] == "real" and budget == 0:
        raise RehearsalError("real budget must be positive")
    limits["budget_usd"] = decimal_text(budget)
    caps = raw["capabilities"]
    if caps != list(CAPABILITIES):
        raise RehearsalError("invalid capabilities")
    catalog = raw["catalog_snapshot"]
    if not isinstance(catalog, dict) or set(catalog) - {"models", "source", "captured_at"} or not isinstance(catalog.get("models"), list):
        raise RehearsalError("invalid catalog_snapshot")
    source = catalog.get("source")
    if raw["mode"] == "offline" and source != "synthetic":
        raise RehearsalError("explicit synthetic catalog required")
    if raw["mode"] == "real" and source not in (None, "openrouter"):
        raise RehearsalError("real catalog required")
    selected = set(models.values())
    frozen = []
    seen = set()
    for item in catalog["models"]:
        required = {"id", "context_length", "max_completion_tokens", "supported_parameters", "pricing"}
        if not isinstance(item, dict) or set(item) != required:
            raise RehearsalError("invalid catalog model")
        model = _model(item["id"])
        if model not in selected or model in seen:
            raise RehearsalError("invalid catalog selection")
        seen.add(model)
        context = _integer(item["context_length"], "context_length", 1, 100_000_000)
        completion = _integer(item["max_completion_tokens"], "max_completion_tokens", 1, 100_000_000)
        if completion < limits["max_output_tokens"] or context < limits["max_output_tokens"] + limits["max_input_bytes"]:
            raise RehearsalError("insufficient model context or completion cap")
        parameters = item["supported_parameters"]
        if (not isinstance(parameters, list) or not 1 <= len(parameters) <= 100
                or any(not isinstance(p, str) or not re.fullmatch(r"[a-z_]{1,80}", p) for p in parameters)
                or len(parameters) != len(set(parameters)) or "max_tokens" not in parameters):
            raise RehearsalError("unsupported model parameters")
        pricing = item["pricing"]
        if not isinstance(pricing, dict) or not {"prompt", "completion", "request"} <= set(pricing):
            raise RehearsalError("unsupported catalog pricing")
        normalized_prices = {}
        for name, value in pricing.items():
            rate = _money(value, "pricing")
            if rate > Decimal("1000") or (name not in ("prompt", "completion", "request") and rate != 0):
                raise RehearsalError("unsupported catalog pricing")
            if name in ("prompt", "completion", "request"):
                normalized_prices[name] = decimal_text(rate)
        frozen.append({"id": model, "context_length": context, "max_completion_tokens": completion,
                       "supported_parameters": sorted(parameters), "pricing": normalized_prices})
    if seen != selected:
        raise RehearsalError("catalog missing selected models")
    snapshot = {"models": sorted(frozen, key=lambda item: item["id"])}
    if source is not None:
        snapshot["source"] = source
    if "captured_at" in catalog:
        captured = catalog["captured_at"]
        try:
            if not isinstance(captured, str) or len(captured) > 64:
                raise ValueError()
            stamp = datetime.fromisoformat(captured.replace("Z", "+00:00"))
            if stamp.utcoffset() is None:
                raise ValueError()
        except ValueError:
            raise RehearsalError("invalid catalog capture time") from None
        snapshot["captured_at"] = captured
    result = {"schema_version": 1, "mode": raw["mode"], "agent_models": models,
              "limits": limits, "catalog_snapshot": snapshot, "capabilities": list(CAPABILITIES)}
    if kind == "day":
        result["kind"] = "day"  # Rehearsal manifests stay byte-identical to before.
    return result


def _choice(value):
    allowed = {"action", "query", "room", "journal_mode", "channels", "source_ids", "release", "name",
               "remember", *CALL_FIELDS}
    if (not isinstance(value, dict) or set(value) - allowed
            or not isinstance(value.get("action"), str) or value["action"] not in CHOICE_ACTIONS):
        raise RehearsalError("invalid choice")
    try:
        validate_call_fields(value)
    except ValueError:
        raise RehearsalError("invalid call") from None
    if "remember" in value:
        try:
            validate_line(value["remember"])
        except ValueError:
            raise RehearsalError("invalid notebook line") from None
    name = value.get("name")
    if (value["action"] == "skill") != ("name" in value) or ("name" in value and (
            not isinstance(name, str) or not 1 <= len(name) <= 64
            or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in name))):
        raise RehearsalError("invalid skill choice")
    if "room" in value and (value["action"] != "library" or value["room"] not in LIBRARY_ROOMS):
        raise RehearsalError("invalid library room")
    if "query" in value:
        query = value["query"]
        if (value["action"] != "library" or not isinstance(query, str) or not query.strip()
                or len(query) > 200 or any(ord(c) < 32 for c in query)):
            raise RehearsalError("invalid library query")
        try:
            if len(query.encode("utf-8")) > 2000:
                raise RehearsalError("invalid library query")
        except UnicodeError:
            raise RehearsalError("invalid library query") from None
    extras = set(value) & {"journal_mode", "channels", "source_ids", "release"}
    if extras and value["action"] != "journal":
        raise RehearsalError("invalid journal choice")
    mode = value.get("journal_mode", "note")
    if not isinstance(mode, str) or mode not in JOURNAL_OPTIONS["modes"]:
        raise RehearsalError("invalid journal mode")
    if "channels" in value:
        channels = value["channels"]
        if (not isinstance(channels, list) or not 1 <= len(channels) <= 3
                or any(not isinstance(c, str) or c not in JOURNAL_OPTIONS["channels"] for c in channels)
                or len(set(channels)) != len(channels)
                or ("unclassified" in channels and channels != ["unclassified"])
                or mode == "witness"):
            raise RehearsalError("invalid journal channels")
    if "source_ids" in value:
        ids = value["source_ids"]
        if (mode != "distill" or not isinstance(ids, list) or not 1 <= len(ids) <= 20
                or any(type(i) is not int or not 1 <= i <= 2**63 - 1 for i in ids)
                or len(set(ids)) != len(ids)):
            raise RehearsalError("invalid source ids")
    if "release" in value and (mode != "distill" or type(value["release"]) is not bool):
        raise RehearsalError("invalid release")
    return _dump(value)


def _refs(value):
    if value is None:
        return "[]"
    if not isinstance(value, list) or len(value) > 128:
        raise RehearsalError("invalid record_refs")
    result = []
    for ref in value:
        if not isinstance(ref, dict) or set(ref) != {"kind", "id"} or ref["kind"] not in ("journal", "episode", "inquiry", "library", "witness", "call"):
            raise RehearsalError("invalid record ref")
        ident = ref["id"]
        if ref["kind"] == "witness":
            _uuid(ident, "record id")
        elif type(ident) is int:
            _integer(ident, "record id", 1, 2**63 - 1)
        elif ref["kind"] == "inquiry":
            _uuid(ident, "record id")
        else:
            _safe(ident, "record id")
        result.append({"kind": ref["kind"], "id": ident})
    return _dump(result)


def counted_usd(request):
    """What one request counts against the budget (docs/specs/BUDGET_ACTUAL_CHARGES.md).

    Only a successful request whose charge the provider reported counts that
    charge. Everything else (in flight, uncertain, failed, never sent, or an
    unknown or estimated charge) keeps its full worst-case set-aside, so the
    guard can never admit more than the budget allows. Failures never release:
    an error can still be billed even when it reports nothing.
    """
    reserved = Decimal(request["reserved_usd"])
    if request["outcome"] != "success":
        return reserved
    usage = json.loads(request["usage"]) if request["usage"] else {}
    if usage.get("cost_status") == "reported" and usage.get("cost_usd") is not None:
        return Decimal(usage["cost_usd"])
    return reserved


def _usage(raw):
    # Only explicitly recognized numeric metadata survives; raw content is never stored.
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise RehearsalError("invalid usage")
    aliases = {"input_tokens": "prompt_tokens", "output_tokens": "completion_tokens"}
    result = {}
    for field in _TOKEN_FIELDS:
        value = raw.get(field, raw.get(aliases.get(field, "")))
        result[field] = None if value is None else _integer(value, field, 0, 10_000_000_000)
    value = raw.get("provider_cost_usd", raw.get("cost_usd", raw.get("cost")))
    result["cost_usd"] = None if value is None else decimal_text(_money(value, "cost_usd"))
    status = raw.get("cost_status", "reported")
    if status not in ("reported", "estimated", "unknown"):
        raise RehearsalError("invalid cost_status")
    result["cost_status"] = "unknown" if value is None else status
    if value is not None and status == "unknown":
        raise RehearsalError("invalid cost coverage")
    return result


_SCHEMA = """
CREATE TABLE runs (
 run_id TEXT PRIMARY KEY, manifest TEXT NOT NULL, status TEXT NOT NULL,
 created_at TEXT NOT NULL, started_at TEXT, ended_at TEXT,
 stop_requested INTEGER NOT NULL DEFAULT 0, controller_token TEXT, deadline REAL
);
CREATE TABLE jobs (
 wake_id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, round INTEGER NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending', action TEXT, failure_code TEXT,
 requested_model TEXT NOT NULL, response_model TEXT, provider TEXT,
 request_count INTEGER NOT NULL DEFAULT 0, duration_ms REAL NOT NULL DEFAULT 0,
 record_refs TEXT NOT NULL DEFAULT '[]', updated_at TEXT NOT NULL,
 choice TEXT, output TEXT, decision_metadata TEXT, private_context TEXT
);
CREATE TABLE requests (
 request_id TEXT PRIMARY KEY, wake_id TEXT NOT NULL REFERENCES jobs(wake_id),
 agent_id TEXT NOT NULL, activity TEXT NOT NULL, requested_model TEXT NOT NULL,
 input_bytes INTEGER NOT NULL, max_output_tokens INTEGER NOT NULL,
 reserved_usd TEXT NOT NULL, created_at TEXT NOT NULL, finished_at TEXT,
 outcome TEXT NOT NULL DEFAULT 'in_flight', response_model TEXT, provider TEXT,
 duration_ms REAL NOT NULL DEFAULT 0, usage TEXT NOT NULL, failure_code TEXT,
 dispatched INTEGER NOT NULL DEFAULT 0, controller_token TEXT NOT NULL, finish_reason TEXT
);
CREATE TABLE request_inputs (
 request_id TEXT PRIMARY KEY REFERENCES requests(request_id),
 messages TEXT NOT NULL, input_sha256 TEXT NOT NULL
);
CREATE TRIGGER immutable_manifest BEFORE UPDATE OF run_id,manifest,created_at ON runs
 BEGIN SELECT RAISE(ABORT,'immutable run'); END;
CREATE TRIGGER immutable_job BEFORE UPDATE OF wake_id,agent_id,round,requested_model ON jobs
 BEGIN SELECT RAISE(ABORT,'immutable job'); END;
CREATE TRIGGER immutable_choice BEFORE UPDATE OF choice ON jobs WHEN OLD.choice IS NOT NULL
 BEGIN SELECT RAISE(ABORT,'immutable choice'); END;
CREATE TRIGGER immutable_output BEFORE UPDATE OF output ON jobs WHEN OLD.output IS NOT NULL
 BEGIN SELECT RAISE(ABORT,'immutable output'); END;
CREATE TRIGGER immutable_request BEFORE UPDATE OF request_id,wake_id,agent_id,activity,requested_model,input_bytes,max_output_tokens,reserved_usd,created_at,controller_token ON requests
 BEGIN SELECT RAISE(ABORT,'immutable request'); END;
CREATE TRIGGER no_delete_requests BEFORE DELETE ON requests
 BEGIN SELECT RAISE(ABORT,'append only requests'); END;
CREATE TRIGGER immutable_decision_metadata BEFORE UPDATE OF decision_metadata ON jobs
 WHEN OLD.decision_metadata IS NOT NULL
 BEGIN SELECT RAISE(ABORT,'immutable decision metadata'); END;
CREATE TRIGGER immutable_private_context BEFORE UPDATE OF private_context ON jobs
 WHEN OLD.private_context IS NOT NULL
 BEGIN SELECT RAISE(ABORT,'immutable private context'); END;
CREATE TRIGGER no_delete_decision_context BEFORE DELETE ON jobs
 WHEN OLD.decision_metadata IS NOT NULL OR OLD.private_context IS NOT NULL
 BEGIN SELECT RAISE(ABORT,'immutable decision context'); END;
CREATE TRIGGER immutable_request_inputs BEFORE UPDATE ON request_inputs
 BEGIN SELECT RAISE(ABORT,'immutable request input'); END;
CREATE TRIGGER no_delete_request_inputs BEFORE DELETE ON request_inputs
 BEGIN SELECT RAISE(ABORT,'append only request inputs'); END;
"""


class RehearsalStore:
    def __init__(self, root):
        try:
            raw = Path(root).expanduser()
        except (TypeError, ValueError):
            raise RehearsalError("invalid run root") from None
        if ".." in raw.parts:
            raise RehearsalError("run root traversal forbidden")
        self.root = Path(os.path.abspath(raw))
        self._check_path(self.root)
        if self.root.exists() and not self.root.is_dir():
            raise RehearsalError("invalid run root")

    @staticmethod
    def _check_path(path):
        # Check every existing component before resolving/opening. Reads never mkdir.
        for item in reversed((path, *path.parents)):
            try:
                mode = item.lstat().st_mode
            except FileNotFoundError:
                continue
            except OSError:
                raise RehearsalError("unavailable run path") from None
            if stat.S_ISLNK(mode):
                raise RehearsalError("symlink run path forbidden")
            if item != path and not stat.S_ISDIR(mode):
                raise RehearsalError("invalid run path")
        return path

    def run_path(self, run_id):
        path = self.root / _uuid(run_id)
        self._check_path(path)
        if path.exists() and not path.is_dir():
            raise RehearsalError("invalid run directory")
        return path

    def safe_run_file(self, run_id, relative):
        """Check fixed run-local files and SQLite sidecars, without creating them.

        This rejects preexisting symlinks, not concurrent tampering by the owner
        of the private (0700) run directories. It does not create missing files.
        """
        if isinstance(relative, Path):
            relative = relative.as_posix()
        if not isinstance(relative, str) or relative not in _RUN_FILES:
            raise RehearsalError("invalid run file")
        path = self.run_path(run_id) / relative
        candidates = [path]
        if path.suffix == ".sqlite3":
            candidates.extend(Path(str(path) + suffix) for suffix in ("-journal", "-wal", "-shm"))
        for candidate in candidates:
            self._check_path(candidate)
            try:
                mode = candidate.lstat().st_mode
            except FileNotFoundError:
                # SQLite sidecars may disappear normally as another worker
                # commits. One stat result avoids exists()/is_file() races.
                continue
            except OSError:
                raise RehearsalError("unavailable run path") from None
            if not stat.S_ISREG(mode):
                raise RehearsalError("invalid run file")
        return path

    def _db_path(self, run_id):
        path = self.safe_run_file(run_id, "control.sqlite3")
        if not path.is_file():
            raise RehearsalError("run not found")
        return path

    @contextmanager
    def _connection(self, run_id, *, write=False):
        path = self._db_path(run_id)
        connection = None
        try:
            connection = sqlite3.connect(path.as_uri() + ("?mode=rw" if write else "?mode=ro"), uri=True, timeout=10)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            if write:
                os.chmod(path, 0o600)
                connection.execute("BEGIN IMMEDIATE")
            yield connection
            if write:
                connection.commit()
        except sqlite3.Error:
            if connection is not None:
                connection.rollback()
            raise RehearsalError("unavailable rehearsal state") from None
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _private_dirs(path):
        missing = []
        current = path
        while not current.exists():
            missing.append(current)
            current = current.parent
        RehearsalStore._check_path(path)
        for item in reversed(missing):
            try:
                item.mkdir(mode=0o700)
            except FileExistsError:
                RehearsalStore._check_path(item)
        if not path.is_dir():
            raise RehearsalError("invalid run root")
        os.chmod(path, 0o700)

    def prepare(self, manifest, *, run_id=None):
        manifest = _validate_manifest(manifest)
        run_id = str(uuid4()) if run_id is None else _uuid(run_id)
        path = self.run_path(run_id)
        self._private_dirs(self.root)
        try:
            path.mkdir(mode=0o700)
        except FileExistsError:
            raise RehearsalConflict("run already exists") from None
        for name in ("memory", "profiles", "library"):
            (path / name).mkdir(mode=0o700)
        db = path / "control.sqlite3"
        fd = os.open(db, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        connection = sqlite3.connect(db)
        try:
            connection.executescript(_SCHEMA)
            now = _now()
            connection.execute("INSERT INTO runs(run_id,manifest,status,created_at) VALUES(?,?,?,?)",
                               (run_id, _dump(manifest), "prepared", now))
            fixed_rounds = 0 if manifest.get("kind") == "day" else manifest["limits"]["wakes_per_agent"]
            for round_number in range(1, fixed_rounds + 1):
                for owner in OWNERS:
                    connection.execute("INSERT INTO jobs(wake_id,agent_id,round,requested_model,updated_at) VALUES(?,?,?,?,?)",
                                       (f"{owner}-r{round_number}", owner, round_number, manifest["agent_models"][owner], now))
            connection.commit()
        except sqlite3.Error:
            raise RehearsalError("unable to prepare rehearsal") from None
        finally:
            connection.close()
        return self.get_run(run_id)

    @staticmethod
    def _run(connection):
        row = connection.execute("SELECT * FROM runs LIMIT 1").fetchone()
        if row is None:
            raise RehearsalError("run not found")
        return row

    @staticmethod
    def _job(connection, wake_id):
        _safe(wake_id, "wake_id")
        row = connection.execute("SELECT * FROM jobs WHERE wake_id=?", (wake_id,)).fetchone()
        if row is None:
            raise RehearsalError("job not found")
        return row

    @staticmethod
    def _token(row, token):
        _uuid(token, "controller token")
        if row["controller_token"] != token:
            raise RehearsalConflict("controller token is not current")

    @classmethod
    def _active(cls, row, token):
        cls._token(row, token)
        if row["stop_requested"] or row["status"] != "running":
            raise RehearsalStopped("rehearsal is stopped")
        if row["deadline"] is None or time.time() >= row["deadline"]:
            raise RehearsalStopped("rehearsal deadline exceeded")

    @staticmethod
    def _context_schema(connection):
        """Add nullable storage only in an explicit write transaction.

        No historical record is reshaped or backfilled. Readers never call this.
        Individual execute calls preserve the caller's atomic transaction (unlike
        executescript, which would implicitly commit the controller checks).
        """
        columns = {row[1] for row in connection.execute("PRAGMA table_info(jobs)")}
        for column in ("decision_metadata", "private_context"):
            if column not in columns:
                connection.execute(f"ALTER TABLE jobs ADD COLUMN {column} TEXT")
        columns = {row[1] for row in connection.execute("PRAGMA table_info(requests)")}
        if "finish_reason" not in columns:
            connection.execute("ALTER TABLE requests ADD COLUMN finish_reason TEXT")
        connection.execute("CREATE TABLE IF NOT EXISTS request_inputs (request_id TEXT PRIMARY KEY REFERENCES requests(request_id), messages TEXT NOT NULL, input_sha256 TEXT NOT NULL)")
        for column in ("decision_metadata", "private_context"):
            connection.execute(f"CREATE TRIGGER IF NOT EXISTS immutable_{column} BEFORE UPDATE OF {column} ON jobs WHEN OLD.{column} IS NOT NULL BEGIN SELECT RAISE(ABORT,'immutable decision context'); END")
        connection.execute("CREATE TRIGGER IF NOT EXISTS no_delete_decision_context BEFORE DELETE ON jobs WHEN OLD.decision_metadata IS NOT NULL OR OLD.private_context IS NOT NULL BEGIN SELECT RAISE(ABORT,'immutable decision context'); END")
        connection.execute("CREATE TRIGGER IF NOT EXISTS immutable_request_inputs BEFORE UPDATE ON request_inputs BEGIN SELECT RAISE(ABORT,'immutable request input'); END")
        connection.execute("CREATE TRIGGER IF NOT EXISTS no_delete_request_inputs BEFORE DELETE ON request_inputs BEGIN SELECT RAISE(ABORT,'append only request inputs'); END")

    @staticmethod
    def _context_value(row):
        if "decision_metadata" not in row.keys() or row["decision_metadata"] is None:
            return None
        return json.loads(row["decision_metadata"])

    @staticmethod
    def _owner_job(job):
        if (job["agent_id"] not in OWNERS or type(job["round"]) is not int
                or not 1 <= job["round"] <= MAX_WAKES_PER_AGENT
                or job["wake_id"] != f"{job['agent_id']}-r{job['round']}"):
            raise RehearsalConflict("job owner linkage is invalid")

    @classmethod
    def _local_context_refs(cls, connection, job, refs, carried=frozenset()):
        """Validate refs against earlier linked jobs, never foreign memory DBs.

        ``carried`` holds this owner's journal/episode/inquiry refs from earlier runs of a
        continuing home; such refs carry no wake_id of this run.
        """
        for ref in refs:
            if "agent_id" in ref and ref["agent_id"] != job["agent_id"]:
                raise RehearsalConflict("context reference is not owner local")
            if "wake_id" not in ref and (ref["kind"], ref["id"]) in carried:
                continue
            sources = connection.execute("SELECT wake_id,agent_id,round,record_refs FROM jobs WHERE agent_id=? AND round<?", (job["agent_id"], job["round"])).fetchall()
            matched = False
            for source in sources:
                cls._owner_job(source)
                if "wake_id" in ref and ref["wake_id"] != source["wake_id"]:
                    continue
                if {"kind": ref["kind"], "id": ref["id"]} in json.loads(source["record_refs"]):
                    matched = True
                    break
            if not matched:
                raise RehearsalConflict("context reference is not owner local")

    def _carried_refs(self, run_id, owner):
        """This owner's carried refs from earlier runs of its home."""
        from .home import CARRIED_REF_KINDS, previous_run_ids
        carried = set()
        for previous in previous_run_ids(self, run_id):
            for row in self.list_jobs(previous):
                if row["agent_id"] == owner:
                    carried.update((ref["kind"], ref["id"]) for ref in row["record_refs"]
                                   if ref["kind"] in CARRIED_REF_KINDS)
        return frozenset(carried)

    @staticmethod
    def _public_job(row):
        fields = ("wake_id", "agent_id", "round", "status", "action", "failure_code", "requested_model",
                  "response_model", "provider", "request_count", "duration_ms", "record_refs", "updated_at")
        result = {field: row[field] for field in fields}
        result["record_refs"] = json.loads(result["record_refs"])
        result["decision_context"] = RehearsalStore._context_value(row)
        result["selection_origin"] = None if result["decision_context"] is None else "none"
        if result["decision_context"] is not None and "choice" in row.keys() and row["choice"] is not None:
            try:
                choice = json.loads(row["choice"])
                _choice(choice)
                if choice["action"] == row["action"]:
                    result["selection_origin"] = "model"
            except (RehearsalError, ValueError, TypeError):
                pass
        if "choice" in row.keys() and row["choice"] is not None:
            try:
                choice = json.loads(row["choice"])
                _choice(choice)
                for field in ("journal_mode", "channels"):
                    if field in choice:
                        result[field] = choice[field]
            except (RehearsalError, ValueError, TypeError):
                pass
        return result

    @classmethod
    def _summary(cls, connection):
        row = cls._run(connection)
        manifest = json.loads(row["manifest"])
        reserved = Decimal(0)
        counted = Decimal(0)
        known = Decimal(0)
        unknown = 0
        requests = connection.execute("SELECT reserved_usd,usage,outcome FROM requests").fetchall()
        for request in requests:
            reserved = decimal_add(reserved, Decimal(request["reserved_usd"]))
            counted = decimal_add(counted, counted_usd(request))
            cost = json.loads(request["usage"])["cost_usd"]
            if cost is None:
                unknown += 1
            else:
                known = decimal_add(known, Decimal(cost))
        agents = []
        for owner in OWNERS:
            counts = {"agent_id": owner, "pending": 0, "completed": 0, "failed": 0, "stopped": 0, "uncertain": 0}
            for job in connection.execute("SELECT status FROM jobs WHERE agent_id=?", (owner,)):
                counts["pending" if job["status"] == "running" else job["status"]] += 1
            agents.append(counts)
        return {"run_id": row["run_id"], "mode": manifest["mode"], **({"kind": "day"} if manifest.get("kind") == "day" else {}),
                "status": row["status"],
                "created_at": row["created_at"], "started_at": row["started_at"], "ended_at": row["ended_at"],
                "stop_requested": bool(row["stop_requested"]), "limits": manifest["limits"],
                "agent_models": manifest["agent_models"], "request_count": len(requests),
                "reserved_usd": decimal_text(reserved), "counted_usd": decimal_text(counted),
                "known_cost_usd": decimal_text(known) if len(requests) > unknown else None,
                "unknown_cost_requests": unknown, "agents": agents, "capabilities": manifest["capabilities"]}

    def get_run(self, run_id):
        with self._connection(run_id) as connection:
            return self._summary(connection)

    def get_manifest(self, run_id):
        with self._connection(run_id) as connection:
            return json.loads(self._run(connection)["manifest"])

    def list_runs(self, limit=20, offset=0):
        _integer(limit, "limit", 1, 100)
        _integer(offset, "offset", 0, 1_000_000)
        self._check_path(self.root)
        if not self.root.exists():
            return {"runs": [], "total": 0, "limit": limit, "offset": offset}
        if not self.root.is_dir():
            raise RehearsalError("invalid run root")
        summaries = []
        for path in self.root.iterdir():
            try:
                _uuid(path.name)
            except RehearsalError:
                continue
            self.run_path(path.name)
            if (path / "control.sqlite3").exists():
                summaries.append(self.get_run(path.name))
        summaries.sort(key=lambda run: (run["created_at"], run["run_id"]), reverse=True)
        return {"runs": summaries[offset:offset + limit], "total": len(summaries), "limit": limit, "offset": offset}

    def list_jobs(self, run_id):
        with self._connection(run_id) as connection:
            rows = connection.execute("SELECT * FROM jobs ORDER BY round, rowid").fetchall()
            return [self._public_job(row) for row in rows]

    def get_witness_snapshot(self, run_id, owner=None):
        """One read snapshot of source facts, never private inputs/output/query.

        Missing legacy offer metadata stays unknown. Scope validation precedes
        any file access; no migrations or source-memory reads occur here.
        """
        if owner is not None and (not isinstance(owner, str) or owner not in OWNERS):
            raise RehearsalError("invalid witness owner")
        with self._connection(run_id) as connection:
            connection.execute("BEGIN")
            row = connection.execute("SELECT run_id,status,created_at,started_at,ended_at,manifest FROM runs LIMIT 1").fetchone()
            if row is None:
                raise RehearsalError("run not found")
            manifest = json.loads(row["manifest"])
            run = {field: row[field] for field in ("run_id", "status", "created_at", "started_at", "ended_at")}
            run["mode"] = manifest["mode"]
            run["prepared_owners"] = [owner] if owner is not None else list(OWNERS)
            columns = {item[1] for item in connection.execute("PRAGMA table_info(jobs)")}
            context = "decision_metadata" if "decision_metadata" in columns else "NULL AS decision_metadata"
            # SQLite projects only classified fields; raw library queries and
            # arbitrary private choice bodies never enter the snapshot reader.
            where, args = ("", ()) if owner is None else (" WHERE agent_id=?", (owner,))
            rows = connection.execute(
                "SELECT wake_id,agent_id,round,status,action,failure_code,request_count,record_refs,"
                + context + ",json_extract(choice,'$.journal_mode') AS journal_mode,"
                "json_extract(choice,'$.channels') AS channels,"
                "CASE WHEN choice IS NULL THEN 0 ELSE 1 END AS choice_committed "
                "FROM jobs" + where + " ORDER BY round,rowid LIMIT ?", (*args, WITNESS_MAX_JOBS)).fetchall()
            jobs = []
            for item in rows:
                # A day run stores each move as its own round, up to MAX_WAKES_PER_AGENT;
                # a two-round rehearsal is the small case of the same bound.
                if (item["agent_id"] not in OWNERS or type(item["round"]) is not int
                        or not 0 <= item["round"] <= MAX_WAKES_PER_AGENT
                        or item["wake_id"] != f"{item['agent_id']}-r{item['round']}"):
                    raise RehearsalConflict("job owner linkage is invalid")
                job = {field: item[field] for field in ("wake_id", "agent_id", "round", "status", "action", "failure_code", "request_count")}
                job["record_refs"] = json.loads(item["record_refs"])
                job["decision_context"] = None if item["decision_metadata"] is None else json.loads(item["decision_metadata"])
                job["choice_committed"] = bool(item["choice_committed"])
                if item["journal_mode"] is not None:
                    job["journal_mode"] = item["journal_mode"]
                if item["channels"] is not None:
                    job["channels"] = json.loads(item["channels"])
                jobs.append(job)
            requests = [dict(item) for item in connection.execute(
                "SELECT request_id,wake_id,agent_id,activity,dispatched,outcome,failure_code "
                "FROM requests" + where + " ORDER BY rowid LIMIT ?", (*args, LIMIT_CAPS["max_requests"]))]
            return {"schema_version": 1, "owner": owner, "run": run,
                    "jobs": jobs, "requests": requests}

    def begin(self, run_id, *, resume=False):
        if type(resume) is not bool:
            raise RehearsalError("invalid resume")
        with self._connection(run_id, write=True) as connection:
            row = self._run(connection)
            if row["controller_token"] is not None:
                raise RehearsalConflict("rehearsal already has a controller; explicit recovery required")
            if row["status"] == "completed":
                raise RehearsalConflict("rehearsal already completed")
            manifest = json.loads(row["manifest"])
            day = manifest.get("kind") == "day"
            if day and row["status"] not in ("prepared", "open") and not resume:
                raise RehearsalConflict("explicit resume required")
            if not day and row["status"] != "prepared" and not resume:
                raise RehearsalConflict("explicit resume required")
            now = time.time()
            # A day run's runtime limit applies to each wake, not to the whole day.
            deadline = (now + manifest["limits"]["max_runtime_seconds"]) if day else (
                row["deadline"] if row["deadline"] is not None else now + manifest["limits"]["max_runtime_seconds"])
            if now >= deadline:
                raise RehearsalStopped("rehearsal deadline exceeded")
            token = str(uuid4())
            connection.execute("UPDATE runs SET status='running', controller_token=?,started_at=COALESCE(started_at,?),ended_at=NULL,stop_requested=0,deadline=?",
                               (token, _now(), deadline))
            if resume:
                missing, unresolved = self._recovery_guards()
                connection.execute("UPDATE jobs SET status='pending',failure_code=NULL,updated_at=? WHERE status IN ('stopped','uncertain') AND NOT " + unresolved + " AND NOT " + missing, (_now(),))
            return token

    def assert_active(self, run_id, token):
        with self._connection(run_id) as connection:
            self._active(self._run(connection), token)

    @staticmethod
    def _settled_status(connection, row):
        statuses = {job[0] for job in connection.execute("SELECT status FROM jobs")}
        if "uncertain" in statuses or connection.execute("SELECT 1 FROM requests WHERE outcome IN ('in_flight','uncertain') LIMIT 1").fetchone():
            return "uncertain"
        if statuses == {"completed"}:
            return "completed"
        if row["stop_requested"] or (row["deadline"] is not None and time.time() >= row["deadline"]):
            return "stopped"
        return "partial"

    @classmethod
    def _day_status(cls, connection, row):
        """An open day stays open between wakes. None for rehearsal runs, or for
        a day that was stopped or left uncertain (those settle as usual)."""
        if json.loads(row["manifest"]).get("kind") != "day" or row["stop_requested"]:
            return None
        settled = cls._settled_status(connection, row)
        return None if settled == "uncertain" else "open"

    def add_wake(self, run_id, owner):
        """Add one owner's next wake to an open day run and return its job.

        No model call. The wake's number is the owner's next sequence number
        today, so continuity treats earlier wakes today as earlier rounds.
        """
        if owner not in OWNERS:
            raise RehearsalError("invalid owner")
        with self._connection(run_id, write=True) as connection:
            row = self._run(connection)
            manifest = json.loads(row["manifest"])
            if manifest.get("kind") != "day":
                raise RehearsalError("wakes are added only to day runs")
            if row["status"] not in ("prepared", "open") or row["stop_requested"]:
                raise RehearsalConflict("day is not open")
            if row["controller_token"] is not None:
                raise RehearsalConflict("a wake is already running")
            previous = connection.execute("SELECT MAX(round) FROM jobs WHERE agent_id=?", (owner,)).fetchone()[0] or 0
            if previous >= manifest["limits"]["wakes_per_agent"]:
                raise RehearsalError("daily wake limit reached")
            unfinished = connection.execute(
                "SELECT 1 FROM jobs WHERE agent_id=? AND status IN ('pending','running','uncertain') LIMIT 1",
                (owner,)).fetchone()
            if unfinished:
                raise RehearsalConflict("an earlier wake for this owner is unfinished")
            round_number = previous + 1
            wake_id = f"{owner}-r{round_number}"
            connection.execute("INSERT INTO jobs(wake_id,agent_id,round,requested_model,updated_at) VALUES(?,?,?,?,?)",
                               (wake_id, owner, round_number, manifest["agent_models"][owner], _now()))
            return self._public_job(self._job(connection, wake_id))

    def give_up_job(self, run_id, wake_id, failure_code):
        """Day runs: end a pending wake that failed again on its retry.

        Only a pending job with no unresolved request, while no controller holds
        the run, so nothing in flight is abandoned.
        """
        failure_code = _safe(failure_code, "failure_code", nullable=False)
        with self._connection(run_id, write=True) as connection:
            row = self._run(connection)
            if json.loads(row["manifest"]).get("kind") != "day":
                raise RehearsalError("only day-run wakes are given up")
            if row["controller_token"] is not None:
                raise RehearsalConflict("a wake is still running")
            job = self._job(connection, wake_id)
            if job["status"] != "pending":
                raise RehearsalConflict("only a waiting wake is given up")
            if connection.execute("SELECT 1 FROM requests WHERE wake_id=? AND outcome IN ('in_flight','uncertain') LIMIT 1",
                                  (wake_id,)).fetchone():
                raise RehearsalConflict("job has an unresolved request")
            connection.execute("UPDATE jobs SET status='failed',failure_code=?,updated_at=? WHERE wake_id=?",
                               (failure_code, _now(), wake_id))

    def close_day(self, run_id):
        """Close an open day run so the next day can continue from it."""
        with self._connection(run_id, write=True) as connection:
            row = self._run(connection)
            if json.loads(row["manifest"]).get("kind") != "day":
                raise RehearsalError("only day runs are closed")
            if row["controller_token"] is not None:
                raise RehearsalConflict("a wake is still running")
            if row["status"] in ("open", "prepared"):
                status = self._settled_status(connection, row)
                connection.execute("UPDATE runs SET status=?,ended_at=?", (status, _now()))
            return self._summary(connection)

    def end(self, run_id, token):
        with self._connection(run_id, write=True) as connection:
            row = self._run(connection)
            self._token(row, token)
            # Ending with an unfinished request cannot authorize a retry.
            self._recover_jobs(connection, stopped=self._is_stopped(row))
            status = self._day_status(connection, row) or self._settled_status(connection, row)
            connection.execute("UPDATE runs SET status=?,controller_token=NULL,ended_at=?", (status, _now()))
            return self._summary(connection)

    def request_stop(self, run_id):
        with self._connection(run_id, write=True) as connection:
            row = self._run(connection)
            if row["status"] != "completed":
                connection.execute("UPDATE runs SET stop_requested=1,status='stopped',ended_at=?", (_now(),))
                connection.execute("UPDATE jobs SET status='stopped',updated_at=? WHERE status='pending'", (_now(),))
            return self._summary(connection)

    def claim_job(self, run_id, wake_id, token):
        with self._connection(run_id, write=True) as connection:
            self._active(self._run(connection), token)
            job = self._job(connection, wake_id)
            if job["status"] != "pending":
                return None
            if connection.execute("SELECT 1 FROM requests WHERE wake_id=? AND outcome IN ('in_flight','uncertain') LIMIT 1", (wake_id,)).fetchone():
                raise RehearsalConflict("uncertain request must not be resent")
            connection.execute("UPDATE jobs SET status='running',updated_at=? WHERE wake_id=?", (_now(), wake_id))
            return self._public_job(self._job(connection, wake_id))

    def commit_choice(self, run_id, wake_id, token, choice):
        serialized = _choice(choice)
        with self._connection(run_id, write=True) as connection:
            # Persisting an already-returned response is not new dispatch.
            self._token(self._run(connection), token)
            row = self._job(connection, wake_id)
            if row["choice"] is not None:
                if row["choice"] == serialized:
                    return
                raise RehearsalConflict("choice is immutable")
            if row["status"] != "running":
                raise RehearsalConflict("job is not claimed")
            connection.execute("UPDATE jobs SET choice=?,action=?,updated_at=? WHERE wake_id=?", (serialized, choice["action"], _now(), wake_id))

    def get_choice(self, run_id, wake_id):
        with self._connection(run_id) as connection:
            value = self._job(connection, wake_id)["choice"]
            return None if value is None else json.loads(value)

    def commit_decision_context(self, run_id, wake_id, token, *, metadata, private_context):
        """Freeze actual pre-choice evidence; never manufacture historical offers."""
        serialized = _decision_metadata(metadata)
        if type(private_context) is not dict:
            raise RehearsalError("invalid private context")
        # A local storage bound only; what reaches the model is bounded by
        # max_input_bytes, which clips continuity to fit. Room for the
        # market window, headlines and posts beside the full continuity.
        private = _bounded_json(private_context, "private context", MAX_PRIVATE_CONTEXT_CHARS)
        # Work on the validated frozen values, not caller-owned mutable objects.
        metadata, private_context = json.loads(serialized), json.loads(private)
        with self._connection(run_id, write=True) as connection:
            run = self._run(connection)
            self._token(run, token)
            job = self._job(connection, wake_id)
            self._owner_job(job)
            if self._context_value(job) is not None:
                if job["decision_metadata"] == serialized and job["private_context"] == private:
                    return
                raise RehearsalConflict("decision context is immutable")
            self._active(run, token)
            if (job["status"] != "running" or job["choice"] is not None
                    or job["output"] is not None or job["action"] is not None
                    or connection.execute("SELECT 1 FROM requests WHERE wake_id=? LIMIT 1", (wake_id,)).fetchone()):
                raise RehearsalConflict("decision context requires a new claimed choice")
            manifest = json.loads(run["manifest"])
            frozen_model = next(item for item in manifest["catalog_snapshot"]["models"]
                                if item["id"] == job["requested_model"])
            expected_model = {"requested_model": job["requested_model"],
                              "context_length": frozen_model["context_length"],
                              "max_completion_tokens": frozen_model["max_completion_tokens"],
                              "catalog_source": manifest["catalog_snapshot"].get("source")}
            if metadata["constraints"] != manifest["limits"] or metadata["model"] != expected_model:
                raise RehearsalConflict("decision context disagrees with frozen assignment")
            carried = self._carried_refs(run_id, job["agent_id"])
            self._local_context_refs(connection, job, metadata["continuity"]["refs"], carried)

            def check_private(item):
                if isinstance(item, list):
                    for child in item:
                        check_private(child)
                elif isinstance(item, dict):
                    if any(key.lower() in {"headers", "authorization", "api_key", "reasoning",
                                           "output", "response", "innermost", "controller_token"}
                           for key in item):
                        raise RehearsalError("invalid private context fields")
                    if "agent_id" in item and item["agent_id"] != job["agent_id"]:
                        raise RehearsalConflict("context reference is not owner local")
                    if "wake_id" in item:
                        source = self._job(connection, item["wake_id"])
                        self._owner_job(source)
                        if source["agent_id"] != job["agent_id"] or source["round"] >= job["round"]:
                            raise RehearsalConflict("context reference is not owner local")
                    if {"kind", "id"} <= set(item):
                        _refs([{"kind": item["kind"], "id": item["id"]}])
                        ref = {key: item[key] for key in ("kind", "id", "wake_id", "agent_id") if key in item}
                        self._local_context_refs(connection, job, [ref], carried)
                    for child in item.values():
                        check_private(child)

            check_private(private_context)
            self._context_schema(connection)
            connection.execute("UPDATE jobs SET decision_metadata=?,private_context=?,updated_at=? WHERE wake_id=?",
                               (serialized, private, _now(), wake_id))

    def get_decision_context(self, run_id, wake_id):
        with self._connection(run_id) as connection:
            job = self._job(connection, wake_id)
            self._owner_job(job)
            return self._context_value(job)

    def get_decision_details(self, run_id, wake_id):
        """Private owner-scoped evidence; absence on legacy reads causes no DDL."""
        with self._connection(run_id) as connection:
            job = self._job(connection, wake_id)
            self._owner_job(job)
            metadata = self._context_value(job)
            if metadata is None or "private_context" not in job.keys() or job["private_context"] is None:
                return None
            snapshots = []
            exists = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='request_inputs'").fetchone()
            if exists:
                rows = connection.execute("SELECT r.*,i.messages,i.input_sha256 FROM requests r JOIN request_inputs i ON i.request_id=r.request_id WHERE r.wake_id=? AND r.agent_id=? ORDER BY r.rowid", (wake_id, job["agent_id"])).fetchall()
                for row in rows:
                    if row["requested_model"] != job["requested_model"]:
                        continue
                    snapshot = {field: row[field] for field in ("request_id", "wake_id", "agent_id", "activity", "requested_model", "input_bytes", "max_output_tokens", "input_sha256")}
                    snapshot["messages"] = json.loads(row["messages"])
                    snapshot["input_coverage"] = "complete"
                    snapshots.append(snapshot)
            return {"metadata": metadata, "private_context": json.loads(job["private_context"]), "requests": snapshots}

    def commit_request_context(self, run_id, request_id, token, messages):
        """Capture literal final role/content inputs before dispatch, once only."""
        _uuid(request_id, "request_id")
        literal, digest, size = _message_input(messages)
        with self._connection(run_id, write=True) as connection:
            run = self._run(connection)
            self._token(run, token)
            request = connection.execute("SELECT * FROM requests WHERE request_id=?", (request_id,)).fetchone()
            if request is None:
                raise RehearsalError("request not found")
            job = self._job(connection, request["wake_id"])
            self._owner_job(job)
            if (request["controller_token"] != token or request["agent_id"] != job["agent_id"]
                    or request["requested_model"] != job["requested_model"]):
                raise RehearsalConflict("request does not match current claimed job")
            exists = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='request_inputs'").fetchone()
            previous = connection.execute("SELECT messages,input_sha256 FROM request_inputs WHERE request_id=?", (request_id,)).fetchone() if exists else None
            if previous is not None:
                if previous["messages"] == literal and previous["input_sha256"] == digest:
                    return
                raise RehearsalConflict("request input is immutable")
            self._active(run, token)
            if job["status"] != "running" or request["dispatched"] or request["outcome"] != "in_flight" or request["finished_at"] is not None:
                raise RehearsalConflict("request input requires an undispatched claimed request")
            if size != request["input_bytes"]:
                raise RehearsalConflict("request input disagrees with admission accounting")
            if size > json.loads(run["manifest"])["limits"]["max_input_bytes"]:
                raise RehearsalBudgetExceeded("request input limit exceeded")
            self._context_schema(connection)
            connection.execute("INSERT INTO request_inputs(request_id,messages,input_sha256) VALUES(?,?,?)", (request_id, literal, digest))

    def commit_output(self, run_id, wake_id, token, content):
        if not isinstance(content, str):
            raise RehearsalError("invalid output")
        try:
            size = len(content.encode("utf-8"))
        except UnicodeError:
            raise RehearsalError("invalid output") from None
        if size > 65536:
            raise RehearsalError("output too large")
        with self._connection(run_id, write=True) as connection:
            self._token(self._run(connection), token)
            row = self._job(connection, wake_id)
            if row["output"] is not None:
                if row["output"] == content:
                    return
                raise RehearsalConflict("output is immutable")
            if row["status"] != "running" or row["choice"] is None:
                raise RehearsalConflict("output requires a claimed choice")
            connection.execute("UPDATE jobs SET output=?,updated_at=? WHERE wake_id=?", (content, _now(), wake_id))

    def get_output(self, run_id, wake_id):
        with self._connection(run_id) as connection:
            return self._job(connection, wake_id)["output"]

    def finish_job(self, run_id, wake_id, token, *, status="completed", action=None, failure_code=None, record_refs=None):
        if not isinstance(status, str) or status not in _TERMINAL:
            raise RehearsalError("invalid job status")
        if action is not None and action not in CHOICE_ACTIONS:
            raise RehearsalError("invalid action")
        failure_code = _safe(failure_code, "failure_code", nullable=True)
        refs = _refs(record_refs)
        with self._connection(run_id, write=True) as connection:
            self._token(self._run(connection), token)
            row = self._job(connection, wake_id)
            actual_action = row["action"] if action is None else action
            if row["choice"] is not None and actual_action != row["action"]:
                raise RehearsalConflict("action disagrees with committed choice")
            if row["status"] in _TERMINAL:
                if (row["status"], row["action"], row["failure_code"], row["record_refs"]) == (status, actual_action, failure_code, refs):
                    return
                raise RehearsalConflict("terminal job is immutable")
            if row["status"] != "running":
                raise RehearsalConflict("job is not claimed")
            if status == "completed" and connection.execute("SELECT 1 FROM requests WHERE wake_id=? AND outcome IN ('in_flight','uncertain') LIMIT 1", (wake_id,)).fetchone():
                raise RehearsalConflict("job has an unresolved request")
            connection.execute("UPDATE jobs SET status=?,action=?,failure_code=?,record_refs=?,updated_at=? WHERE wake_id=?",
                               (status, actual_action, failure_code, refs, _now(), wake_id))

    def reserve_request(self, run_id, wake_id, token, *, agent_id, activity, model, input_bytes, max_output_tokens, reserved_usd):
        if agent_id not in OWNERS:
            raise RehearsalError("invalid agent_id")
        if activity not in (*CAPABILITIES, "choice", "choose_action", "inquiry", "skill"):
            raise RehearsalError("invalid activity")
        model = _model(model)
        _integer(input_bytes, "input_bytes", 0, DAY_MAX_INPUT_BYTES)
        _integer(max_output_tokens, "max_output_tokens", 1, DAY_MAX_OUTPUT_TOKENS)  # And the run's own limit below.
        amount = _money(reserved_usd, "reserved_usd")
        with self._connection(run_id, write=True) as connection:
            row = self._run(connection)
            self._active(row, token)
            job = self._job(connection, wake_id)
            manifest = json.loads(row["manifest"])
            limits = manifest["limits"]
            if job["status"] != "running" or job["agent_id"] != agent_id or job["requested_model"] != model:
                raise RehearsalConflict("request does not match claimed job")
            if activity in ("choice", "choose_action") and job["choice"] is not None:
                raise RehearsalConflict("committed choice must not be regenerated")
            if activity not in ("choice", "choose_action") and job["output"] is not None:
                raise RehearsalConflict("committed output must not be regenerated")
            if input_bytes > limits["max_input_bytes"] or max_output_tokens > limits["max_output_tokens"]:
                raise RehearsalBudgetExceeded("request input or output limit exceeded")
            requests = connection.execute("SELECT reserved_usd,usage,outcome,wake_id,activity FROM requests").fetchall()
            if any(request["wake_id"] == wake_id and request["outcome"] in ("uncertain", "in_flight") for request in requests):
                raise RehearsalConflict("unresolved request must not be resent")
            choice_request = activity in ("choice", "choose_action")
            if any(request["wake_id"] == wake_id and request["outcome"] == "success"
                   and (request["activity"] in ("choice", "choose_action")) == choice_request for request in requests):
                raise RehearsalConflict("successful request must not be resent")
            if len(requests) >= limits["max_requests"] or job["request_count"] >= 2:
                raise RehearsalBudgetExceeded("request attempt limit exceeded")
            if sum(request["outcome"] == "in_flight" for request in requests) >= limits["max_parallelism"]:
                raise RehearsalConflict("request parallelism limit exceeded")
            # The new request is held at its full set-aside; earlier ones count
            # what the provider actually charged once it is reported.
            total = amount
            for request in requests:
                total = decimal_add(total, counted_usd(request))
            if total > _money(limits["budget_usd"], "budget_usd"):
                raise RehearsalBudgetExceeded("USD admission budget exceeded")
            request_id = str(uuid4())
            now = _now()
            connection.execute("INSERT INTO requests(request_id,wake_id,agent_id,activity,requested_model,input_bytes,max_output_tokens,reserved_usd,created_at,usage,controller_token) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                               (request_id, wake_id, agent_id, activity, model, input_bytes, max_output_tokens, decimal_text(amount), now, _dump(_usage(None)), token))
            connection.execute("UPDATE jobs SET request_count=request_count+1,updated_at=? WHERE wake_id=?", (now, wake_id))
            return request_id

    def mark_dispatched(self, run_id, request_id, token):
        """Atomically commit dispatch immediately before transport, never twice.

        Reservation alone does not authorize transport. Stop/deadline and this
        logical dispatch point serialize through the same write transaction.
        """
        _uuid(request_id, "request_id")
        with self._connection(run_id, write=True) as connection:
            self._active(self._run(connection), token)
            request = connection.execute("SELECT * FROM requests WHERE request_id=?", (request_id,)).fetchone()
            if request is None:
                raise RehearsalError("request not found")
            job = self._job(connection, request["wake_id"])
            if (request["controller_token"] != token or job["status"] != "running"
                    or request["agent_id"] != job["agent_id"]
                    or request["requested_model"] != job["requested_model"]):
                raise RehearsalConflict("request does not match current claimed job")
            if request["dispatched"] or request["outcome"] != "in_flight" or request["finished_at"] is not None:
                raise RehearsalConflict("request is already dispatched or finished")
            connection.execute("UPDATE requests SET dispatched=1 WHERE request_id=?", (request_id,))

    def finish_request(self, run_id, request_id, *, outcome, response_model=None, provider=None, duration_ms=0, usage=None, failure_code=None, finish_reason=None):
        _uuid(request_id, "request_id")
        if not isinstance(outcome, str) or outcome not in _OUTCOMES:
            raise RehearsalError("invalid outcome")
        finish_reason = None if finish_reason is None else (
            finish_reason if isinstance(finish_reason, str) and finish_reason in _FINISH_REASONS else "unknown")
        response_model = None if response_model is None else _model(response_model)
        provider = _safe(provider, "provider", nullable=True, label=True)
        failure_code = _safe(failure_code, "failure_code", nullable=True)
        if isinstance(duration_ms, bool) or not isinstance(duration_ms, (int, float)) or not math.isfinite(duration_ms) or not 0 <= duration_ms <= 86_400_000:
            raise RehearsalError("invalid duration_ms")
        serialized = _dump(_usage(usage))
        with self._connection(run_id, write=True) as connection:
            row = connection.execute("SELECT * FROM requests WHERE request_id=?", (request_id,)).fetchone()
            if row is None:
                raise RehearsalError("request not found")
            values = (outcome, response_model, provider, duration_ms, serialized, failure_code, finish_reason)
            if outcome == "not_sent" and row["dispatched"]:
                raise RehearsalConflict("dispatched request cannot be not sent")
            previous = tuple(row[field] for field in ("outcome", "response_model", "provider", "duration_ms", "usage", "failure_code"))
            previous += (row["finish_reason"] if "finish_reason" in row.keys() else None,)
            if row["outcome"] != "in_flight":
                if previous == values:
                    return
                raise RehearsalConflict("request result is immutable")
            self._context_schema(connection)
            now = _now()
            connection.execute("UPDATE requests SET outcome=?,response_model=?,provider=?,duration_ms=?,usage=?,failure_code=?,finish_reason=?,finished_at=? WHERE request_id=?", (*values, now, request_id))
            connection.execute("UPDATE jobs SET response_model=COALESCE(?,response_model),provider=COALESCE(?,provider),duration_ms=duration_ms+?,updated_at=? WHERE wake_id=?",
                               (response_model, provider, duration_ms, now, row["wake_id"]))

    def list_requests(self, run_id, limit=50, offset=0, agent_id=None):
        _integer(limit, "limit", 1, 100)
        _integer(offset, "offset", 0, 1_000_000)
        if agent_id is not None and agent_id not in OWNERS:
            raise RehearsalError("invalid agent_id")
        with self._connection(run_id) as connection:
            where = "" if agent_id is None else " WHERE agent_id=?"
            args = () if agent_id is None else (agent_id,)
            total = connection.execute("SELECT COUNT(*) FROM requests" + where, args).fetchone()[0]
            rows = connection.execute("SELECT * FROM requests" + where + " ORDER BY rowid LIMIT ? OFFSET ?", (*args, limit, offset)).fetchall()
            events = []
            for row in rows:
                result = {field: row[field] for field in ("request_id", "wake_id", "agent_id", "activity", "requested_model", "input_bytes", "max_output_tokens", "reserved_usd", "created_at", "finished_at", "outcome", "response_model", "provider", "duration_ms", "failure_code")}
                result["finish_reason"] = row["finish_reason"] if "finish_reason" in row.keys() else None
                result.update(json.loads(row["usage"]))
                events.append(result)
            return {"events": events, "total": total, "limit": limit, "offset": offset}

    @staticmethod
    def _is_stopped(row):
        return bool(row["stop_requested"] or (row["deadline"] is not None and time.time() >= row["deadline"]))

    @staticmethod
    def _recovery_guards():
        # Only returned successful work needs a durable private checkpoint.
        missing = "((choice IS NULL AND EXISTS (SELECT 1 FROM requests WHERE requests.wake_id=jobs.wake_id AND outcome='success' AND activity IN ('choice','choose_action'))) OR (output IS NULL AND EXISTS (SELECT 1 FROM requests WHERE requests.wake_id=jobs.wake_id AND outcome='success' AND activity NOT IN ('choice','choose_action'))))"
        unresolved = "EXISTS (SELECT 1 FROM requests WHERE requests.wake_id=jobs.wake_id AND outcome IN ('in_flight','uncertain'))"
        return missing, unresolved

    @classmethod
    def _recover_jobs(cls, connection, *, stopped=False):
        now = _now()
        connection.execute("UPDATE requests SET outcome='not_sent',finished_at=?,failure_code=? WHERE outcome='in_flight' AND dispatched=0",
                           (now, "admission_stopped" if stopped else "interrupted_before_dispatch"))
        connection.execute("UPDATE requests SET outcome='uncertain',finished_at=?,failure_code='interrupted' WHERE outcome='in_flight' AND dispatched=1", (now,))
        connection.execute("UPDATE jobs SET status='uncertain',failure_code='interrupted',updated_at=? WHERE status NOT IN ('completed','failed') AND wake_id IN (SELECT wake_id FROM requests WHERE outcome='uncertain')", (now,))
        # A successful response without its private checkpoint is also unsafe:
        # replaying it could cause another paid request. Preserve it as uncertain.
        missing, unresolved = cls._recovery_guards()
        connection.execute("UPDATE jobs SET status='uncertain',failure_code='missing_checkpoint',updated_at=? WHERE status IN ('running','stopped','uncertain') AND NOT " + unresolved + " AND " + missing, (now,))
        if stopped:
            connection.execute("UPDATE jobs SET status='stopped',updated_at=? WHERE status IN ('pending','running') AND NOT " + unresolved + " AND NOT " + missing, (now,))
        else:
            # Existing stopped progress is only unstopped by explicit resume.
            connection.execute("UPDATE jobs SET status='pending',failure_code=NULL,updated_at=? WHERE status IN ('running','uncertain') AND NOT " + unresolved + " AND NOT " + missing, (now,))

    def recover(self, run_id):
        with self._connection(run_id, write=True) as connection:
            row = self._run(connection)
            if row["status"] == "completed":
                return self._summary(connection)
            self._recover_jobs(connection, stopped=self._is_stopped(row))
            status = self._day_status(connection, row) or self._settled_status(connection, row)
            connection.execute("UPDATE runs SET controller_token=NULL,status=?,ended_at=?", (status, _now()))
            return self._summary(connection)
