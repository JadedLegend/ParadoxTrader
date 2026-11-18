"""Check connection: the OpenRouter key and every model chosen in Settings.

Run from the Settings page. Costs nothing:

- The key is checked with OpenRouter's key endpoint (no generation).
- Each distinct model is looked up in the public catalog.
- A free model gets one tiny reply test with every price cap at zero, so a
  provider that would charge refuses instead. Free tests count toward
  OpenRouter's free-model request limit.
- A paid model gets an endpoint check only: is any provider serving it now.
  No paid generation is sent.

Every result names the agents that use the model. The key never appears in
the result; OpenRouter's own error text is shortened and scrubbed of it.

The dashboard has no internet on purpose, so it never runs the check itself.
It leaves a request file under ``<settings>/check/``; a small separate service
that may go online (paradoxtrader-check, started by a systemd path unit) runs
``run_pending`` and leaves ``result.json`` for the page to read.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

API = "https://openrouter.ai/api/v1"
TIMEOUT_SECONDS = 12
COOLDOWN_SECONDS = 15
FREE_LIMITS_URL = "https://openrouter.ai/collections/free-models"
_STATUS_WORDS = {
    400: "OpenRouter refused the request",
    401: "the key was rejected",
    402: "the account is out of credits",
    403: "the request was blocked by the provider",
    404: "no provider can serve this model right now",
    408: "the model took too long to answer",
    429: "rate limited (free models have a daily request limit)",
    502: "the model's provider failed",
    503: "no provider is available right now",
}


def slot_name(slot):
    return slot.replace("_", " ").title()


def _is_free(model_id, row):
    if model_id.endswith(":free"):
        return True
    pricing = (row or {}).get("pricing") or {}
    try:
        return all(Decimal(str(pricing.get(part, "0") or "0")) == 0
                   for part in ("prompt", "completion", "request"))
    except InvalidOperation:
        return False


class _Checker:
    def __init__(self, key, http_get, http_post):
        self.key, self.http_get, self.http_post = key, http_get, http_post

    def _headers(self):
        return {"Authorization": "Bearer " + self.key, "Content-Type": "application/json"}

    def _scrub(self, text):
        text = " ".join(str(text).split())[:160]
        return text.replace(self.key, "[key]") if self.key else text

    def _error(self, response, data):
        status = getattr(response, "status_code", None)
        detail = data.get("error") if isinstance(data, dict) else None
        detail = detail.get("message") if isinstance(detail, dict) else detail
        words = _STATUS_WORDS.get(status, f"OpenRouter answered {status}")
        return f"{words}: {self._scrub(detail)}" if detail else words

    def _call(self, method, url, **kwargs):
        try:
            response = method(url, timeout=TIMEOUT_SECONDS, allow_redirects=False, **kwargs)
        except Exception as error:  # Network trouble: say so, never raise into the page.
            return None, None, f"could not reach OpenRouter ({type(error).__name__})"
        try:
            data = response.json()
        except Exception:
            data = None
        return response, data, None

    def key_state(self):
        if not self.key:
            return {"status": "fail", "message": "No OpenRouter key is saved."}
        response, data, problem = self._call(self.http_get, API + "/key", headers=self._headers())
        if problem:
            return {"status": "fail", "message": problem}
        if response.status_code != 200 or not isinstance(data, dict) or not isinstance(data.get("data"), dict):
            return {"status": "fail", "message": self._error(response, data)}
        info = data["data"]
        notes, status = ["The key works."], "ok"
        if info.get("is_free_tier"):
            status = "warn"
            notes.append("This account has never bought credits, so paid models will be refused "
                         "and free models have a small daily limit.")
        remaining = info.get("limit_remaining")
        if isinstance(remaining, (int, float)):
            notes.append(f"${remaining:.2f} left on this key's spending limit.")
            if remaining <= 0:
                status = "warn"
        return {"status": status, "message": " ".join(notes), "free_tier": bool(info.get("is_free_tier"))}

    def catalog(self):
        response, data, problem = self._call(self.http_get, API + "/models")
        if problem or response.status_code != 200 or not isinstance(data, dict):
            return None
        return {row["id"]: row for row in data.get("data", []) if isinstance(row, dict) and "id" in row}

    def free_test(self, model):
        payload = {"model": model, "max_tokens": 32, "stream": False,
                   "messages": [{"role": "user", "content": "Reply with the single word OK."}],
                   "provider": {"max_price": {"prompt": 0, "completion": 0, "request": 0}}}
        response, data, problem = self._call(self.http_post, API + "/chat/completions",
                                             headers=self._headers(), json=payload)
        if problem:
            return "fail", problem
        if response.status_code != 200 or not isinstance(data, dict) or data.get("error"):
            return "fail", self._error(response, data)
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            return "fail", "OpenRouter answered, but with no reply"
        choice = choices[0]
        content = (choice.get("message") or {}).get("content")
        if isinstance(content, str) and content.strip():
            return "ok", "Answered the test."
        if choice.get("finish_reason") == "length":
            return "warn", "Started answering but ran out of room on the tiny test; it may think at length."
        return "warn", "Answered with an empty reply."

    def endpoint_check(self, model):
        author, _, slug = model.partition("/")
        url = f"{API}/models/{quote(author, safe='')}/{quote(slug, safe='')}/endpoints"
        response, data, problem = self._call(self.http_get, url, headers=self._headers())
        if problem:
            return "fail", problem
        if response.status_code != 200 or not isinstance(data, dict):
            return "fail", self._error(response, data)
        endpoints = (data.get("data") or {}).get("endpoints") or []
        if not endpoints:
            return "fail", "No provider is serving this model right now."
        count = len(endpoints)
        return "ok", f"{count} provider{'s' if count != 1 else ''} serving it. No paid test was sent."


def check_connection(key, models, *, http_get=None, http_post=None, now=None):
    """``models`` maps each slot (seven agents and the witness) to a model id or None."""
    if http_get is None or http_post is None:
        import requests
        http_get, http_post = http_get or requests.get, http_post or requests.post
    checker = _Checker(key, http_get, http_post)
    key_state = checker.key_state()
    by_model = {}
    for slot, model in models.items():
        if model:
            by_model.setdefault(model, []).append(slot_name(slot))
    unset = [slot_name(slot) for slot, model in models.items() if not model]
    catalog = checker.catalog() if by_model else {}

    def one(model):
        used_by = by_model[model]
        row = catalog.get(model) if catalog is not None else None
        if catalog is not None and row is None:
            return {"model": model, "used_by": used_by, "kind": "unknown", "status": "fail",
                    "message": "OpenRouter does not list this model. It may have been renamed or retired."}
        free = _is_free(model, row)
        if free:
            if key_state["status"] == "fail":
                status, message = "fail", "Not tested: the key is not working."
            else:
                status, message = checker.free_test(model)
        else:
            status, message = checker.endpoint_check(model)
            if status == "ok" and key_state.get("free_tier"):
                status, message = "warn", message + " This account has no credits, so it will be refused."
        return {"model": model, "used_by": used_by, "kind": "free" if free else "paid",
                "status": status, "message": message}

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(one, sorted(by_model)))
    statuses = [key_state["status"]] + [item["status"] for item in results]
    agents_unset = [name for name in unset if name != "Witness"]  # The witness's model is optional for now.
    overall = "fail" if "fail" in statuses else "warn" if "warn" in statuses or agents_unset else "ok"
    stamp = (now or (lambda: datetime.now(timezone.utc)))().isoformat()
    return {"checked_at": stamp, "status": overall,
            "key": {"status": key_state["status"], "message": key_state["message"]},
            "models": results, "unset": unset, "free_limits_url": FREE_LIMITS_URL}


# ---- request and answer files (dashboard <-> check service) -----------------
def _check_dir(settings_dir):
    return Path(settings_dir) / "check"


def _write_json(path, value):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid4().hex}"
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _read_json(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _now_iso(now=None):
    return (now or (lambda: datetime.now(timezone.utc)))().isoformat()


def check_state(settings_dir):
    """What the page shows: a pending request, the last answer, or nothing yet."""
    folder = _check_dir(settings_dir)
    request = _read_json(folder / "request.json")
    result = _read_json(folder / "result.json")
    return {"state": "pending" if request else "done" if result else "none",
            "requested_at": (request or {}).get("requested_at"), "result": result}


def request_check(settings_dir, *, now=None):
    """Leave a request for the check service. A repeat click while one is
    pending, or within a few seconds of the last answer, adds nothing."""
    folder = _check_dir(settings_dir)
    state = check_state(settings_dir)
    if state["state"] == "pending":
        return state
    last = (state["result"] or {}).get("checked_at")
    stamp = _now_iso(now)
    if last:
        try:
            age = (datetime.fromisoformat(stamp) - datetime.fromisoformat(last)).total_seconds()
        except ValueError:
            age = COOLDOWN_SECONDS
        if 0 <= age < COOLDOWN_SECONDS:
            return state
    _write_json(folder / "request.json", {"requested_at": stamp})
    return check_state(settings_dir)


def run_pending(settings_dir, *, check=None, now=None):
    """Run by the check service: answer a pending request, then clear it."""
    from core.runtime.owner_settings import OwnerSettings
    folder = _check_dir(settings_dir)
    request = folder / "request.json"
    if not request.exists():
        return None
    try:
        store = OwnerSettings(settings_dir)
        try:
            result = (check or check_connection)(store.key(), store.models())
        except Exception as error:  # Always leave an answer; never the key.
            result = {"checked_at": _now_iso(now), "status": "fail", "models": [], "unset": [],
                      "free_limits_url": FREE_LIMITS_URL,
                      "key": {"status": "fail", "message": f"The check itself failed ({type(error).__name__})."}}
        _write_json(folder / "result.json", result)
        return result
    finally:
        try:
            request.unlink()
        except FileNotFoundError:
            pass
