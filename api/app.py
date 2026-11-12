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

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from core.forum.store import ForumStore
from core.messaging.store import MessagingStore
from core.trading.alpaca import TradeQueue
from core.memory.engine import ThresholdMemory
from core.runtime.bootstrap import COMMUNITY_WELCOME, seed_agent_canon
from data.feeds.free_feeds import get_market_snapshot

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    _auto_init()
    start_scheduler()
    yield
    stop_scheduler()

app = FastAPI(title="Paradox Edge Trader v2", version="2.0.0", lifespan=lifespan)

# CORS — allow the React frontend (same origin in production, localhost in dev)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


@app.get("/api/forum")
def get_forum_posts(limit: int = 50, thread_id: Optional[str] = None):
    forum = get_forum()
    if thread_id:
        posts = forum.get_thread(thread_id, limit=limit)
    else:
        posts = forum.get_recent(limit=limit)
    return {"posts": posts}


@app.post("/api/forum")
def post_to_forum(req: ForumPostRequest):
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
    messaging = get_messaging()
    mid = messaging.send(sender=req.sender, recipient=req.recipient, content=req.content)
    return {"id": mid, "status": "sent"}


@app.get("/api/queue")
def get_trade_queue():
    queue = get_trade_queue()
    return {"trades": queue.get_pending()}


@app.post("/api/queue/{trade_id}/approve")
def approve_trade(trade_id: int, req: TradeReviewRequest):
    queue = get_trade_queue()
    queue.approve(trade_id, req.notes)
    return {"status": "approved", "id": trade_id}


@app.post("/api/queue/{trade_id}/reject")
def reject_trade(trade_id: int, req: TradeReviewRequest):
    queue = get_trade_queue()
    queue.reject(trade_id, req.notes)
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
                "model": soul.get("model", ""),
                "current_focus": living.get("current_focus", ""),
                "curiosity_questions": living.get("curiosity_questions", []),
                "hrv": round(hrv.hrv, 1) if hrv else None,
                "in_interval": hrv.in_interval if hrv else False,
            })
        except Exception as e:
            result.append({"agent_id": agent_id, "error": str(e)})
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
    """
    Aggregate open Alpaca positions across all 7 agents.
    Returns a map of agent_id -> list of positions.
    Used for cross-agent position visibility (map of attention).
    """
    from core.trading.alpaca import AlpacaClient
    result = {}
    cfg = load_config_yaml()
    agent_keys = cfg.get("alpaca_accounts", {})
    for agent_id in AGENTS:
        keys = agent_keys.get(agent_id, {})
        api_key = keys.get("api_key") or os.environ.get(f"ALPACA_{agent_id.upper()}_API_KEY")
        api_secret = keys.get("api_secret") or os.environ.get(f"ALPACA_{agent_id.upper()}_API_SECRET")
        if not api_key or not api_secret:
            result[agent_id] = {"error": "no_credentials"}
            continue
        try:
            client = AlpacaClient(api_key=api_key, api_secret=api_secret)
            positions = client.get_positions()
            result[agent_id] = positions
        except Exception as e:
            result[agent_id] = {"error": str(e)}
    return {"positions": result}


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
def update_config(req: ConfigUpdateRequest):
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
