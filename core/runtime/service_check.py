"""Check connection for the saved data, news and paper-account keys.

Runs with the OpenRouter check in the networked check service. Every check
is one small read-only request:

- Alpaca (each agent's paper key): the paper account endpoint. Never orders.
- Alpha Vantage, FMP, Massive, Unusual Whales: one quote or ticker-info read
  for SPY. Alpha Vantage's free plan allows 25 such reads a day.
- EODHD: the user endpoint (no data read).
- Brave Search: one search with one result; it uses one query of the plan.
- Reddit through redditapis.com: one post from r/stocks (about $0.0015).
- X: the usage endpoint, which reads no posts.

Never called, by design: Public.com, eToro and SignalStack. They can act on
an account, and a SignalStack webhook would send a signal. Bigdata.com offers
no free key check, so it is not called either.

No key is ever written into a result. Provider text is shortened and scrubbed.
"""
from concurrent.futures import ThreadPoolExecutor

TIMEOUT_SECONDS = 12
_WORDS = {401: "the key was rejected", 403: "the key is not allowed to do this",
          404: "the check address was not found", 429: "rate limited for now"}


def _agent_name(agent):
    return agent.replace("_", " ").title()


class _Service:
    def __init__(self, secrets, http_get, http_post):
        self.secrets, self.http_get, self.http_post = secrets, http_get, http_post

    def _scrub(self, text):
        text = " ".join(str(text).split())[:140]
        for value in self.secrets:
            if value and len(value) >= 6:
                text = text.replace(value, "[key]")
        return text

    def _call(self, method, url, **kwargs):
        try:
            response = method(url, timeout=TIMEOUT_SECONDS, allow_redirects=False, **kwargs)
        except Exception as error:
            return None, None, f"could not reach it ({type(error).__name__})"
        try:
            data = response.json()
        except Exception:
            data = None
        return response, data, None

    def _http_problem(self, response, data):
        status = getattr(response, "status_code", None)
        words = _WORDS.get(status, f"it answered {status}")
        detail = None
        if isinstance(data, dict):
            detail = data.get("message") or data.get("error") or data.get("detail") or data.get("Error Message")
            if isinstance(detail, dict):
                detail = detail.get("message")
        return f"{words}: {self._scrub(detail)}" if isinstance(detail, str) and detail else words


def _row(name, group, status, message):
    return {"service": name, "group": group, "status": status, "message": message}


def check_services(secret, *, http_get, http_post):
    """``secret(slot)`` returns a saved value or None. Returns one row per service."""
    from core.runtime.owner_settings import AGENTS, SECRET_SLOTS
    values = {slot: secret(slot) for slot in SECRET_SLOTS}
    svc = _Service([v for v in values.values() if v], http_get, http_post)
    jobs = []

    def unset(name, group, note="Not set."):
        return lambda: _row(name, group, "unset", note)

    for agent in AGENTS:
        key_id, key_secret = values[f"alpaca_{agent}_key_id"], values[f"alpaca_{agent}_secret"]
        name = f"Alpaca paper: {_agent_name(agent)}"
        if not key_id or not key_secret:
            jobs.append(unset(name, "paper", "Not set." if not (key_id or key_secret) else "Only half of this pair is set."))
            continue

        def alpaca(name=name, key_id=key_id, key_secret=key_secret):
            response, data, problem = svc._call(
                svc.http_get, "https://paper-api.alpaca.markets/v2/account",
                headers={"APCA-API-KEY-ID": key_id, "APCA-API-SECRET-KEY": key_secret})
            if problem:
                return _row(name, "paper", "fail", problem)
            if response.status_code != 200 or not isinstance(data, dict):
                return _row(name, "paper", "fail", svc._http_problem(response, data))
            state = data.get("status")
            if state != "ACTIVE":
                return _row(name, "paper", "warn", f"The paper account answered, but its status is {svc._scrub(state)}.")
            return _row(name, "paper", "ok", "Paper account active. Nothing was ordered.")
        jobs.append(alpaca)

    def simple(name, group, slot, url, *, params=None, headers=None, ok=None, note=""):
        value = values[slot]
        if not value:
            return unset(name, group)

        def run():
            response, data, problem = svc._call(svc.http_get, url, params=params(value) if params else None,
                                                headers=headers(value) if headers else None)
            if problem:
                return _row(name, group, "fail", problem)
            if response.status_code != 200:
                return _row(name, group, "fail", svc._http_problem(response, data))
            verdict = ok(data) if ok else None
            if verdict:
                return _row(name, group, "fail", svc._scrub(verdict))
            return _row(name, group, "ok", ("The key works. " + note).strip())
        return run

    def alphavantage_ok(data):
        if not isinstance(data, dict):
            return "it sent nothing usable"
        for field in ("Error Message", "Information", "Note"):
            if data.get(field):
                return data[field]
        return None if data.get("Global Quote") else "it sent no quote"

    def has_data(data):
        return None if data not in (None, [], {}) else "it sent nothing back"

    jobs += [
        simple("Alpha Vantage", "data", "alphavantage", "https://www.alphavantage.co/query",
               params=lambda v: {"function": "GLOBAL_QUOTE", "symbol": "SPY", "apikey": v},
               ok=alphavantage_ok, note="Used 1 of the free plan's 25 daily reads."),
        simple("FMP", "data", "fmp", "https://financialmodelingprep.com/stable/quote",
               params=lambda v: {"symbol": "SPY", "apikey": v}, ok=has_data),
        simple("Massive", "data", "massive", "https://api.massive.com/v3/reference/tickers/SPY",
               params=lambda v: {"apiKey": v}, ok=has_data),
        simple("Unusual Whales", "data", "unusual_whales", "https://api.unusualwhales.com/api/stock/SPY/info",
               headers=lambda v: {"Authorization": "Bearer " + v, "Accept": "application/json"}, ok=has_data),
        simple("EODHD", "data", "eodhd", "https://eodhd.com/api/user",
               params=lambda v: {"api_token": v, "fmt": "json"}, ok=has_data),
        simple("Brave Search", "news", "brave_search", "https://api.search.brave.com/res/v1/web/search",
               params=lambda v: {"q": "stock market", "count": 1},
               headers=lambda v: {"X-Subscription-Token": v, "Accept": "application/json"},
               note="Used 1 search from the plan."),
        simple("X", "news", "x_bearer_token", "https://api.x.com/2/usage/tweets",
               headers=lambda v: {"Authorization": "Bearer " + v}, ok=has_data,
               note="Checked with the usage endpoint, which reads no posts."),
    ]

    jobs.append(simple("Reddit", "news", "redditapis_token", "https://api.redditapis.com/api/reddit/posts",
                       params=lambda v: {"subreddit": "stocks", "sort": "hot", "limit": 1},
                       headers=lambda v: {"Authorization": "Bearer " + v}, ok=has_data,
                       note="Used 1 read (about $0.0015)."))
    for slot, name in (("bigdata", "Bigdata.com"), ("public_com", "Public.com"), ("etoro_api_key", "eToro"),
                       ("signalstack_webhook", "SignalStack")):
        why = ("It has no free key check, so it is not called." if slot == "bigdata"
               else "Stored only. Never called: it can act on an account.")
        group = "data" if slot == "bigdata" else "broker"
        jobs.append((lambda name=name, slot=slot, why=why, group=group:
                     _row(name, group, "skipped" if values[slot] else "unset", why if values[slot] else "Not set.")))

    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(lambda job: job(), jobs))
