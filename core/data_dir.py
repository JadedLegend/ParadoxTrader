"""
Data Directory Resolution — Paradox Edge Trader v2
====================================================
All SQLite databases and persistent files must live in DATA_DIR.

Priority:
  1. DATA_DIR env var (explicit override)
  2. Render persistent disk: /opt/render/project/src/data
  3. Local fallback: {REPO_ROOT}/data

This ensures HRV states, agent memories, forum posts, and messages
all survive Render deploys and restarts.
"""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


def get_data_dir() -> Path:
    # Explicit override
    if os.environ.get("DATA_DIR"):
        p = Path(os.environ["DATA_DIR"])
        p.mkdir(parents=True, exist_ok=True)
        return p

    # Render persistent disk
    render_disk = Path("/opt/render/project/src/data")
    if render_disk.parent.parent.exists():
        render_disk.mkdir(parents=True, exist_ok=True)
        return render_disk

    # Local fallback
    local = REPO_ROOT / "data"
    local.mkdir(parents=True, exist_ok=True)
    return local


DATA_DIR = get_data_dir()


def db_path(filename: str) -> str:
    """Return the full path for a database file in DATA_DIR."""
    return str(DATA_DIR / filename)


def agent_db_path(agent_id: str) -> str:
    """Return the memory database path for a specific agent."""
    agent_dir = DATA_DIR / "agents" / agent_id
    agent_dir.mkdir(parents=True, exist_ok=True)
    return str(agent_dir / "memory.sqlite3")
