"""
Paradox Edge Trader v2 — FastAPI Backend
==========================================
All agent systems exposed as REST endpoints.
The React frontend talks exclusively to this API.

Endpoints:
  GET  /api/status              — All agent HRV states
  GET  /api/forum               — Recent forum posts
  POST /api/forum               — Post to forum (user or agent)
  GET  /api/inbox/{agent_id}    — Agent inbox
  POST /api/dm                  — Send direct message
  GET  /api/queue               — Pending trade queue
  POST /api/queue/{id}/approve  — Approve a trade
  POST /api/queue/{id}/reject   — Reject a trade
  GET  /api/snapshot            — Market snapshot
  GET  /api/config              — Current system config (keys redacted)
  POST /api/config              — Update config values
  POST /api/phase               — Set developmental phase
  POST /api/countdown           — Set Phase 2 countdown
  POST /api/init                — Initialize system
  POST /api/wake/{agent_id}     — Manually trigger agent wake
  GET  /api/agents              — All agent soul + living data
  GET  /api/agents/{agent_id}/journal — Agent's journal entries
  GET  /api/agents/{agent_id}/episodes — Agent's recent episodes
  GET  /api/announcements       — Latest announcements + countdown
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional

# Ensure repo root is in path
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from fastapi import FastAPI, HTTPException, BackgroundTasks, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from core.forum.store import ForumStore
from core.messaging.store import MessagingStore
from core.trading.alpaca import TradeQueue
from core.memory.engine import ThresholdMemory
from core.runtime.bootstrap import COMMUNITY_WELCOME, seed_agent_canon
from core.runtime.community import get_community_policy
from data.feeds.free_feeds import get_market_snapshot
from core.library import get_library

from core.usage import get_usage_store
from core.trading.lineage.errors import LineageAccessError, LineageNotFound
from contextlib import asynccontextmanager
from core.runtime.scheduler import start_scheduler, stop_scheduler

def _auto_init():
    """
    Idempotent startup initializer.
    Ensures every agent has HRV state, working guidance, and optional originals.
    Safe to run on every restart — skips existing canon title/source identities.
    Does NOT write agent reflections or overwrite existing memory or config.
    """
    import logging
    log = logging.getLogger("startup")
    try:
        from core.memory.engine import ThresholdMemory
        from core.hrv.engine import HRVStore

        hrv_store = HRVStore(db_path("hrv.sqlite3"))

        for agent_id in AGENTS:
            soul_path = REPO_ROOT / "agents" / agent_id / "soul.json"
            mem = ThresholdMemory(agent_db_path(agent_id))

            if seed_agent_canon(mem):
                log.info(f"Auto-init: seeded {agent_id}")

            # Always ensure HRV state exists
            hrv_store.load(agent_id, soul_path=str(soul_path))

        # Ensure the general forum thread exists
        from core.forum.store import ForumStore
        forum = ForumStore()
        forum.create_thread("general", "General Discussion", "SYSTEM")  # no-op if already exists
        log.info("Auto-init complete.")
    except Exception as e:
        import logging as _l
        _l.getLogger("startup").error(f"Auto-init failed (non-fatal): {e}", exc_info=True)


def _legacy_scheduler_enabled():
    """The legacy scheduler wakes every agent and spends model credit; it is opt-in only."""
    return os.environ.get("PARADOX_LEGACY_SCHEDULER", "").strip() == "1"


def _legacy_app_allowed():
    """The broad legacy app may only be served deliberately, for local development.

    start.sh checks the same variable, but `uvicorn api.app:app` would bypass a
    check that lives only in the script, so the app enforces it at startup too.
    Importing the module (as tests do) is unaffected; serving it is refused.
    """
    return os.environ.get("PARADOX_ALLOW_LEGACY_APP", "").strip() == "1"


def _legacy_allowed_origins():
    raw = os.environ.get("PARADOX_LEGACY_ALLOWED_ORIGINS",
                         "http://localhost:5173,http://127.0.0.1:5173")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not _legacy_app_allowed():
        raise RuntimeError("legacy_app_disabled: set PARADOX_ALLOW_LEGACY_APP=1 only for "
                           "deliberate local development; use scripts/rehearsal.py and the "
                           "private gateway instead")
    _auto_init()
    scheduler_enabled = _legacy_scheduler_enabled()
    if scheduler_enabled:
        start_scheduler()
    yield
    if scheduler_enabled:
        stop_scheduler()

app = FastAPI(title="Paradox Edge Trader v2", version="2.0.0", lifespan=lifespan)

# CORS — the built frontend is same-origin and the Vite dev server proxies /api,
# so only the local dev origins are allowed, and never with credentials.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_legacy_allowed_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)


_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@app.middleware("http")
async def _reject_cross_site_writes(request, call_next):
    """CORS does not stop a web page from *sending* a simple POST (e.g. /api/wake/x).

    Browsers always attach Origin to cross-origin writes, so refuse any write whose
    Origin is neither this server nor an allowed dev origin. Requests without an
    Origin header (curl, the CLI) are unaffected.
    """
    origin = request.headers.get("origin")
    if request.method in _UNSAFE_METHODS and origin:
        own = f"{request.url.scheme}://{request.url.netloc}"
        if origin != own and origin not in _legacy_allowed_origins():
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "cross_origin_write_refused"}, status_code=403)
    return await call_next(request)

AGENTS = ["tempest", "siren", "alchemist", "weaver", "oracle", "shadow", "paradox_hunter"]

from core.data_dir import DATA_DIR, db_path, agent_db_path


# ─── Helpers ─────────────────────────────────────────────────────────────────────────────────

def get_hrv_store():
    from core.hrv.engine import HRVStore
    return HRVStore(db_path("hrv.sqlite3"))

def get_forum():
    return ForumStore()

def get_messaging():
    return MessagingStore()

def get_trade_queue():
    return TradeQueue(db_path("trade_queue.sqlite3"))

def get_agent_memory(agent_id: str) -> ThresholdMemory:
    return ThresholdMemory(agent_db_path(agent_id))

def load_soul(agent_id: str) -> dict:
    with open(REPO_ROOT / "agents" / agent_id / "soul.json") as f:
        return json.load(f)

def load_living(agent_id: str) -> dict:
    with open(REPO_ROOT / "agents" / agent_id / "living.json") as f:
        return json.load(f)

def load_config_yaml() -> dict:
    """
    Load order:
      1. DATA_DIR/system.yaml  — persistent disk (survives redeploys, written by save_config_yaml)
      2. REPO_ROOT/config/system.yaml  — local dev override (gitignored)
      3. REPO_ROOT/config/system.example.yaml  — shipped defaults
    """
    try:
        import yaml
        # 1. Persistent disk config (Render)
        persistent_path = DATA_DIR / "system.yaml"
        if persistent_path.exists():
            with open(persistent_path) as f:
                return yaml.safe_load(f) or {}
        # 2. Local dev system.yaml
        local_path = REPO_ROOT / "config" / "system.yaml"
        if local_path.exists():
            with open(local_path) as f:
                return yaml.safe_load(f) or {}
        # 3. Example config (shipped defaults)
        example_path = REPO_ROOT / "config" / "system.example.yaml"
        with open(example_path) as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}

def save_config_yaml(cfg: dict):
    """Always save to DATA_DIR/system.yaml so changes persist on Render."""
    import yaml
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cfg_path = DATA_DIR / "system.yaml"
    with open(cfg_path, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)


# ─── Models ───────────────────────────────────────────────────────────────────

class ForumPostRequest(BaseModel):
    author: str = "user"
    content: str
    thread_id: str = "general"
    reply_to: Optional[int] = None
    tags: Optional[list] = None

class DMRequest(BaseModel):
    sender: str
    recipient: str
    content: str

class ConfigUpdateRequest(BaseModel):
    key_path: str   # dot-notation, e.g. "guardrails.autonomous_trading_mode"
    value: object

class PhaseRequest(BaseModel):
    phase: int

class CountdownRequest(BaseModel):
    target_iso: str  # ISO 8601 datetime

class TradeReviewRequest(BaseModel):
    notes: str = ""

class SelfDefinitionRequest(BaseModel):
    definition: str

class InnermostRequest(BaseModel):
    content: str


# ─── Routes ───────────────────────────────────────────────────────────────────

def _require_lineage_operator(authorization):
    """Server-owned capability, never a caller-selected role or phase."""
    import hmac
    token = os.environ.get("LINEAGE_OPERATOR_TOKEN", "")
    if not token or not token.strip():
        raise HTTPException(status_code=503, detail="lineage_operator_unavailable") from None
    try:
        expected = ("Bearer " + token).encode("utf-8")
    except UnicodeError:
        raise HTTPException(status_code=503, detail="lineage_operator_unavailable") from None
    try:
        provided = authorization.encode("utf-8") if isinstance(authorization, str) else b""
    except UnicodeError:
        provided = b""
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=403, detail="lineage_operator_required") from None


def get_lineage_store():
    """Resolve the existing queue-backed store only after read authorization."""
    from core.trading.lineage import LineageStore
    return LineageStore(db_path("trade_queue.sqlite3"))


def _lineage_pilot(agent_id):
    if agent_id not in AGENTS:
        raise HTTPException(status_code=404, detail="lineage_agent_not_found") from None


def _lineage_integer(value, minimum, maximum):
    if isinstance(value, str) and len(value) <= 10 and value.isascii() and value.isdecimal():
        value = int(value)
    if type(value) is not int or not minimum <= value <= maximum:
        raise HTTPException(status_code=400, detail="invalid_lineage_request") from None
    return value


@app.get("/api/lineage/inquiries")
def lineage_inquiries(agent_id: str = "alchemist", limit: int | str = 50, offset: int | str = 0,
                      authorization: Optional[str] = Header(None)):
    """Bounded operator metadata read; no agent, broker, or private-memory calls."""
    _require_lineage_operator(authorization)
    _lineage_pilot(agent_id)
    limit = _lineage_integer(limit, 1, 50)
    offset = _lineage_integer(offset, 0, 2**31 - 1)
    try:
        return get_lineage_store().list_inquiries(agent_id, operator=True, limit=limit, offset=offset)
    except LineageAccessError:
        raise HTTPException(status_code=403, detail="lineage_access_denied") from None
    except LineageNotFound:
        raise HTTPException(status_code=404, detail="lineage_inquiry_not_found") from None
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid_lineage_request") from None
    except Exception:
        raise HTTPException(status_code=503, detail="lineage_unavailable") from None


@app.get("/api/lineage/inquiries/{inquiry_id}")
def lineage_inquiry(inquiry_id: str, agent_id: str = "alchemist",
                    authorization: Optional[str] = Header(None)):
    """Read one selected owner's inquiry; no mismatched owner passes the gate."""
    import re
    _require_lineage_operator(authorization)
    _lineage_pilot(agent_id)
    if not isinstance(inquiry_id, str) or not re.fullmatch(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", inquiry_id):
        raise HTTPException(status_code=400, detail="invalid_lineage_request") from None
    try:
        result = get_lineage_store().get_inquiry(inquiry_id, operator=True)
        if result["inquiry"]["agent_id"] != agent_id:
            raise LineageNotFound("outside selected owner")
        return result
    except LineageAccessError:
        raise HTTPException(status_code=403, detail="lineage_access_denied") from None
    except LineageNotFound:
        raise HTTPException(status_code=404, detail="lineage_inquiry_not_found") from None
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid_lineage_request") from None
    except Exception:
        raise HTTPException(status_code=503, detail="lineage_unavailable") from None


@app.get("/api/usage/summary")
def usage_summary(agent_id: Optional[str] = None, since: Optional[str] = None, until: Optional[str] = None):
    """Read aggregate request metadata; never starts providers or agent activity."""
    import re
    from datetime import datetime
    try:
        if agent_id is not None and (not isinstance(agent_id, str) or not re.fullmatch(r"[a-zA-Z0-9_.:-]{1,80}", agent_id)):
            raise ValueError("invalid filter")
        dates = []
        for value in (since, until):
            if value is None:
                dates.append(None)
                continue
            if not isinstance(value, str) or len(value) > 64 or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})", value, flags=re.ASCII):
                raise ValueError("invalid timestamp")
            if not value.endswith("Z") and (int(value[-5:-3]) > 23 or int(value[-2:]) > 59):
                raise ValueError("invalid timezone offset")
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ValueError("timezone required")
            dates.append(parsed)
        if dates[0] is not None and dates[1] is not None and dates[0] > dates[1]:
            raise ValueError("invalid time range")
        return get_usage_store().summary(agent_id=agent_id, since=since, until=until)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid_usage_request") from None
    except Exception:
        raise HTTPException(status_code=503, detail="usage_unavailable") from None


@app.get("/api/usage/events")
def usage_events(agent_id: Optional[str] = None, limit: int | str = 50, offset: int | str = 0,
                 since: Optional[str] = None, until: Optional[str] = None):
    """Read at most 100 metadata events with explicit, strict pagination."""
    import re
    from datetime import datetime
    try:
        if isinstance(limit, str) and len(limit) <= 10 and limit.isascii() and limit.isdecimal():
            limit = int(limit)
        if isinstance(offset, str) and len(offset) <= 10 and offset.isascii() and offset.isdecimal():
            offset = int(offset)
        if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or not 0 <= offset <= 2**31 - 1:
            raise ValueError("invalid pagination")
        if agent_id is not None and (not isinstance(agent_id, str) or not re.fullmatch(r"[a-zA-Z0-9_.:-]{1,80}", agent_id)):
            raise ValueError("invalid filter")
        dates = []
        for value in (since, until):
            if value is None:
                dates.append(None)
                continue
            if not isinstance(value, str) or len(value) > 64 or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})", value, flags=re.ASCII):
                raise ValueError("invalid timestamp")
            if not value.endswith("Z") and (int(value[-5:-3]) > 23 or int(value[-2:]) > 59):
                raise ValueError("invalid timezone offset")
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ValueError("timezone required")
            dates.append(parsed)
        if dates[0] is not None and dates[1] is not None and dates[0] > dates[1]:
            raise ValueError("invalid time range")
        return get_usage_store().list_events(agent_id=agent_id, limit=limit, offset=offset, since=since, until=until)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid_usage_request") from None
    except Exception:
        raise HTTPException(status_code=503, detail="usage_unavailable") from None


@app.get("/api/library/documents")
def library_documents(limit: int | str = 50, offset: int | str = 0):
    """Browse imported metadata only, without reading originals or agent stores."""
    try:
        # Accept decimal HTTP query strings; let the store reject every other type.
        if isinstance(limit, str) and len(limit) <= 10 and limit.isascii() and limit.isdecimal():
            limit = int(limit)
        if isinstance(offset, str) and len(offset) <= 10 and offset.isascii() and offset.isdecimal():
            offset = int(offset)
        return get_library().list_documents(limit=limit, offset=offset)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid_library_request") from None
    except Exception:
        raise HTTPException(status_code=503, detail="library_unavailable") from None


@app.get("/api/library/search")
def library_search(q: str, document_id: Optional[str] = None, limit: int | str = 3, max_chars: int | str = 600):
    """Search lexical source terms; identifiers are not filenames or file paths."""
    try:
        if isinstance(limit, str) and len(limit) <= 10 and limit.isascii() and limit.isdecimal():
            limit = int(limit)
        if isinstance(max_chars, str) and len(max_chars) <= 10 and max_chars.isascii() and max_chars.isdecimal():
            max_chars = int(max_chars)
        return get_library().search(q, document_id=document_id, limit=limit, max_chars=max_chars)
    except KeyError:
        raise HTTPException(status_code=404, detail="library_document_not_found") from None
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid_library_request") from None
    except Exception:
        raise HTTPException(status_code=503, detail="library_unavailable") from None


@app.get("/api/library/sections/{section_id}")
def library_section(section_id: str, offset: int | str = 0, max_chars: int | str = 1200):
    """Read a bounded section window while preserving its extraction locator."""
    try:
        if isinstance(offset, str) and len(offset) <= 10 and offset.isascii() and offset.isdecimal():
            offset = int(offset)
        if isinstance(max_chars, str) and len(max_chars) <= 10 and max_chars.isascii() and max_chars.isdecimal():
            max_chars = int(max_chars)
        return get_library().read_section(section_id, offset=offset, max_chars=max_chars)
    except KeyError:
        raise HTTPException(status_code=404, detail="library_section_not_found") from None
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid_library_request") from None
    except Exception:
        raise HTTPException(status_code=503, detail="library_unavailable") from None


@app.get("/api/status")
def get_status():
    store = get_hrv_store()
    states = store.get_all_states()
    return {
        "agents": [
            {
                "agent_id": s.agent_id,
                "hrv": round(s.hrv, 1),
                "max_hrv": s.max_hrv,
                "in_interval": s.in_interval,
                "last_tick_at": s.last_tick_at,
            }
            for s in states
        ]
    }


def _require_community_access(gate):
    from core.runtime.config import get_runtime_config
    runtime = get_runtime_config()
    phase = runtime.get("current_phase", 0) if isinstance(runtime, dict) else 0
    if type(phase) is not int or phase < 1 or not get_community_policy(runtime)[gate]:
        raise HTTPException(status_code=403, detail="community_access_closed")


@app.get("/api/forum")
def get_forum_posts(limit: int = 50, thread_id: Optional[str] = None):
    _require_community_access("forum_open")
    forum = get_forum()
    if thread_id:
        posts = forum.get_thread(thread_id, limit=limit)
    else:
        posts = forum.get_recent(limit=limit)
    return {"posts": posts}


@app.post("/api/forum")
def post_to_forum(req: ForumPostRequest):
    _require_community_access("forum_open")
    forum = get_forum()
    pid = forum.post(
        author=req.author,
        content=req.content,
        thread_id=req.thread_id,
        reply_to=req.reply_to,
        tags=req.tags or [],
    )
    return {"id": pid, "status": "posted"}


@app.get("/api/forum/threads")
def get_threads():
    _require_community_access("forum_open")
    forum = get_forum()
    return {"threads": forum.list_threads()}


@app.get("/api/inbox/{agent_id}")
def get_inbox(agent_id: str, unread_only: bool = False):
    if agent_id not in AGENTS and agent_id != "user":
        raise HTTPException(status_code=404, detail="Agent not found")
    messaging = get_messaging()
    msgs = messaging.get_inbox(agent_id, unread_only=unread_only, limit=50)
    return {"messages": msgs, "unread_count": messaging.unread_count(agent_id)}


@app.post("/api/dm")
def send_dm(req: DMRequest):
    if req.sender not in AGENTS and req.sender != "user":
        raise HTTPException(status_code=404, detail="Sender not found")
    if req.recipient not in AGENTS and req.recipient != "user":
        raise HTTPException(status_code=404, detail="Recipient not found")
    if req.sender in AGENTS and req.recipient in AGENTS:
        _require_community_access("peer_messages_open")
    messaging = get_messaging()
    mid = messaging.send(sender=req.sender, recipient=req.recipient, content=req.content)
    return {"id": mid, "status": "sent"}


@app.get("/api/queue")
def get_pending_trades():
    queue = get_trade_queue()
    return {"trades": queue.get_pending()}


@app.post("/api/queue/{trade_id}/approve")
def approve_trade(trade_id: int, req: TradeReviewRequest, authorization: Optional[str] = Header(default=None)):
    queue = get_trade_queue()
    entry = queue.get_entry(trade_id)
    if entry and entry.get("lineage_proposal_id"):
        _require_lineage_operator(authorization)
        if len(req.notes) > 2000:
            raise HTTPException(status_code=400, detail="invalid_lineage_review")
    if not queue.approve(trade_id, req.notes):
        raise HTTPException(status_code=409, detail="trade_review_conflict")
    return {"status": "approved", "id": trade_id}


@app.post("/api/queue/{trade_id}/reject")
def reject_trade(trade_id: int, req: TradeReviewRequest, authorization: Optional[str] = Header(default=None)):
    queue = get_trade_queue()
    entry = queue.get_entry(trade_id)
    if entry and entry.get("lineage_proposal_id"):
        _require_lineage_operator(authorization)
        if len(req.notes) > 2000:
            raise HTTPException(status_code=400, detail="invalid_lineage_review")
    if not queue.reject(trade_id, req.notes):
        raise HTTPException(status_code=409, detail="trade_review_conflict")
    return {"status": "rejected", "id": trade_id}


@app.get("/api/snapshot")
def market_snapshot():
    try:
        snap = get_market_snapshot()
        return snap
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/agents")
def get_all_agents():
    """Read profiles and existing HRV states without initializing agents.

    Missing HRV and capacity remain unknown (None); model names are profile
    preferences, not resolved provider configuration. No config/model calls,
    wake, scheduler, or profile/state writes belong in this handler.
    """
    result = []
    store = get_hrv_store()
    hrv_states = {s.agent_id: s for s in store.get_all_states()}
    for agent_id in AGENTS:
        try:
            soul = load_soul(agent_id)
            living = load_living(agent_id)
            hrv = hrv_states.get(agent_id)
            result.append({
                "agent_id": agent_id,
                "name": soul.get("name", agent_id),
                "epistemic_role": soul.get("epistemic_role", ""),
                "core_drive": soul.get("core_drive", ""),
                "model": soul.get("model_preference") or soul.get("model", ""),
                "current_focus": living.get("current_focus", ""),
                "curiosity_questions": living.get("curiosity_questions", []),
                "hrv": round(hrv.hrv, 1) if hrv else None,
                "max_hrv": hrv.max_hrv if hrv else None,
                "hrv_status": "ok" if hrv else "not_initialized",
                "in_interval": hrv.in_interval if hrv else False,
            })
        except Exception:
            result.append({"agent_id": agent_id, "error": "profile_unavailable"})
    return {"agents": result}


@app.get("/api/agents/{agent_id}/journal")
def get_journal(agent_id: str, limit: int = 20):
    if agent_id not in AGENTS:
        raise HTTPException(status_code=404, detail="Agent not found")
    mem = get_agent_memory(agent_id)
    entries = mem.read_journal(limit=limit)
    return {"agent_id": agent_id, "entries": entries}


@app.get("/api/agents/{agent_id}/episodes")
def get_episodes(agent_id: str, limit: int = 20):
    if agent_id not in AGENTS:
        raise HTTPException(status_code=404, detail="Agent not found")
    mem = get_agent_memory(agent_id)
    episodes = mem.get_recent_episodes(limit=limit)
    return {"agent_id": agent_id, "episodes": episodes}


@app.get("/api/agents/{agent_id}/self-definition")
def get_self_definition(agent_id: str):
    """Return the agent's current self_definition and revision history."""
    if agent_id not in AGENTS:
        raise HTTPException(status_code=404, detail="Agent not found")
    soul = load_soul(agent_id)
    return {
        "agent_id": agent_id,
        "name": soul.get("name", agent_id),
        "self_definition": soul.get("self_definition", ""),
        "self_definition_history": soul.get("self_definition_history", []),
    }


@app.post("/api/agents/{agent_id}/self-definition")
def update_self_definition(agent_id: str, req: SelfDefinitionRequest):
    """
    Allow an agent to revise their self_definition.
    The previous definition is archived in self_definition_history.
    A flag is set in the living.json to notify the user.
    """
    if agent_id not in AGENTS:
        raise HTTPException(status_code=404, detail="Agent not found")
    soul_path = REPO_ROOT / "agents" / agent_id / "soul.json"
    soul = load_soul(agent_id)
    previous = soul.get("self_definition", "")
    history = soul.get("self_definition_history", [])
    from datetime import datetime, timezone
    history.append({
        "definition": previous,
        "archived_at": datetime.now(timezone.utc).isoformat(),
    })
    soul["self_definition"] = req.definition
    soul["self_definition_history"] = history
    with open(soul_path, "w") as f:
        import json as _json
        _json.dump(soul, f, indent=2, ensure_ascii=False)
    # Flag in living.json for user review
    living_path = REPO_ROOT / "agents" / agent_id / "living.json"
    try:
        with open(living_path) as f:
            living = json.load(f)
        living["self_definition_revised"] = True
        living["self_definition_revised_at"] = datetime.now(timezone.utc).isoformat()
        with open(living_path, "w") as f:
            json.dump(living, f, indent=2, ensure_ascii=False)
    except Exception:
        pass
    return {
        "status": "updated",
        "agent_id": agent_id,
        "previous": previous,
        "new": req.definition,
        "flagged_for_review": True,
    }


@app.get("/api/agents/positions")
def get_all_positions():
    """Delegate read-only position snapshots to the shared runtime helper.

    Return {"positions": {agent_id: snapshot}} unchanged. Each snapshot has
    status (ok/error/not_configured), a positions list, and observed_at. An
    empty list confirms no positions only when status is ok; failures remain
    unknown. The helper owns credential lookup and safe error categories;
    this wrapper neither reads config nor constructs broker clients.
    """
    from core.runtime import agent_loop
    return {"positions": agent_loop.get_cross_agent_positions(AGENTS)}


@app.post("/api/agents/{agent_id}/innermost")
def write_innermost_entry(agent_id: str, req: InnermostRequest, background_tasks: BackgroundTasks):
    """
    Write to the agent's innermost journal layer.
    Enforces a 3-minute cooldown between entries.
    This layer is not retrieved, not scored, not displayed in the UI.
    It is simply kept.
    """
    if agent_id not in AGENTS:
        raise HTTPException(status_code=404, detail="Agent not found")
    mem = get_agent_memory(agent_id)
    from datetime import datetime, timezone, timedelta
    last_ts = mem.last_innermost_ts()
    if last_ts:
        last_dt = datetime.fromisoformat(last_ts)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds()
        if elapsed < 180:  # 3 minutes
            remaining = int(180 - elapsed)
            raise HTTPException(
                status_code=429,
                detail=f"Cooldown active. {remaining} seconds remaining."
            )
    entry_id = mem.write_innermost(req.content)
    return {"status": "written", "id": entry_id, "agent_id": agent_id}


@app.post("/api/agents/{agent_id}/journal")
def write_journal_entry(agent_id: str, req: InnermostRequest):
    """
    Write a journal entry for an agent from the always-accessible sidebar.
    Enforces a 3-minute cooldown between entries.
    """
    if agent_id not in AGENTS:
        raise HTTPException(status_code=404, detail="Agent not found")
    mem = get_agent_memory(agent_id)
    from datetime import datetime, timezone, timedelta
    # Check last journal entry time
    entries = mem.read_journal(limit=1)
    if entries:
        last_ts = entries[0].get("created_at", "")
        try:
            last_dt = datetime.fromisoformat(last_ts)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds()
            if elapsed < 180:
                remaining = int(180 - elapsed)
                raise HTTPException(
                    status_code=429,
                    detail=f"Cooldown active. {remaining} seconds remaining."
                )
        except (ValueError, TypeError):
            pass
    mem.write_journal(req.content, mood="sidebar", hrv_at_writing=None)
    return {"status": "written", "agent_id": agent_id}


@app.get("/api/config")
def get_config():
    cfg = load_config_yaml()
    # Redact all API keys before sending to frontend
    def redact(obj):
        if isinstance(obj, dict):
            return {
                k: ("***" if any(s in k.lower() for s in ["key", "secret", "token", "password"]) else redact(v))
                for k, v in obj.items()
            }
        return obj
    return {"config": redact(cfg)}


@app.post("/api/config")
def update_config(req: ConfigUpdateRequest, authorization: Optional[str] = Header(default=None)):
    _require_lineage_operator(authorization)
    if req.key_path.split(".")[0] == "guardrails":
        raise HTTPException(status_code=403, detail="guardrails_not_writable_via_api")
    cfg = load_config_yaml()
    parts = req.key_path.split(".")
    node = cfg
    for part in parts[:-1]:
        if part not in node:
            node[part] = {}
        node = node[part]
    node[parts[-1]] = req.value
    save_config_yaml(cfg)
    # Reload config cache
    from core.runtime import config as cfg_module
    cfg_module._config_cache = None
    return {"status": "updated", "key": req.key_path, "value": req.value}


@app.post("/api/phase")
def set_phase(req: PhaseRequest):
    if req.phase not in [0, 1, 2, 3]:
        raise HTTPException(status_code=400, detail="Phase must be 0, 1, 2, or 3")
    cfg = load_config_yaml()
    cfg.setdefault("runtime", {})["current_phase"] = req.phase
    save_config_yaml(cfg)
    from core.runtime import config as cfg_module
    cfg_module._config_cache = None
    # Post announcement to forum
    forum = get_forum()
    phase_names = {0: "Solo Incubation", 1: "Forum Opens", 2: "Countdown", 3: "Council Mode"}
    forum.post_announcement(
        content=f"Phase advanced to Phase {req.phase}: {phase_names.get(req.phase, '')}.",
        author="SYSTEM",
    )
    return {"status": "phase set", "phase": req.phase}


@app.post("/api/countdown")
def set_countdown(req: CountdownRequest):
    forum = get_forum()
    fid = forum.post_announcement(
        content=f"The council converges on {req.target_iso}. The countdown has begun.",
        author="SYSTEM",
        is_countdown=True,
        countdown_target=req.target_iso,
    )
    return {"status": "countdown set", "target": req.target_iso, "id": fid}


@app.get("/api/announcements")
def get_announcements():
    forum = get_forum()
    announcements = forum.get_latest_announcements(limit=10)
    countdown = forum.get_countdown()
    return {"announcements": announcements, "countdown": countdown}


@app.post("/api/init")
def init_system():
    """Seed missing guidance and HRV states; record a SYSTEM welcome."""
    from core.memory.engine import ThresholdMemory

    hrv_store = get_hrv_store()
    initialized = []

    for agent_id in AGENTS:
        soul_path = REPO_ROOT / "agents" / agent_id / "soul.json"
        mem = ThresholdMemory(agent_db_path(agent_id))
        seed_agent_canon(mem)
        hrv_store.load(agent_id, soul_path=str(soul_path))
        initialized.append(agent_id)

    forum = get_forum()
    forum.create_thread("general", "General Discussion", "SYSTEM")
    forum.post(
        author="SYSTEM",
        content=COMMUNITY_WELCOME,
        thread_id="general",
        phase="symmetry",
    )

    return {"status": "initialized", "agents": initialized}


@app.post("/api/wake/{agent_id}")
def wake_agent(agent_id: str, background_tasks: BackgroundTasks):
    if agent_id not in AGENTS:
        raise HTTPException(status_code=404, detail="Agent not found")
    from core.runtime.agent_loop import agent_wake
    from core.runtime.config import get_runtime_config
    phase = int(get_runtime_config().get("current_phase", 0))

    def run_wake():
        agent_wake(agent_id, phase=phase)

    background_tasks.add_task(run_wake)
    return {"status": "wake triggered", "agent": agent_id}


# ─── Serve React frontend ─────────────────────────────────────────────────────

FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}")
    def serve_frontend(full_path: str):
        index = FRONTEND_DIST / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return {"error": "Frontend not built yet"}
else:
    @app.get("/")
    def root():
        return {
            "message": "Paradox Edge Trader v2 API",
            "docs": "/docs",
            "status": "Frontend not yet built. Run: cd frontend && npm install && npm run build",
        }
