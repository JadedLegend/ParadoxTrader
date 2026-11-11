"""
Config Loader — Paradox Edge Trader v2
========================================
Loads config/system.yaml. Falls back gracefully to example config.
Provides typed access to all settings.
"""

import os
from pathlib import Path
from typing import Any, Optional

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "system.yaml"
EXAMPLE_PATH = Path(__file__).parent.parent.parent / "config" / "system.example.yaml"

# Persistent disk config path (Render) — checked first
def _persistent_config_path() -> Path:
    from core.data_dir import DATA_DIR
    return DATA_DIR / "system.yaml"

_config_cache: Optional[dict] = None


def load_config(force_reload: bool = False) -> dict:
    global _config_cache
    if _config_cache and not force_reload:
        return _config_cache

    # Load order: persistent disk → local system.yaml → example config
    persistent = _persistent_config_path()
    if persistent.exists():
        path = persistent
    elif CONFIG_PATH.exists():
        path = CONFIG_PATH
    else:
        path = EXAMPLE_PATH

    if yaml is None:
        raise ImportError("PyYAML is required. Run: pip install pyyaml")

    with open(path) as f:
        cfg = yaml.safe_load(f)

    # Allow env var overrides for secrets
    if os.environ.get("OPENROUTER_API_KEY"):
        cfg.setdefault("openrouter", {})["api_key"] = os.environ["OPENROUTER_API_KEY"]

    if os.environ.get("FMP_API_KEY"):
        cfg.setdefault("fmp", {})["api_key"] = os.environ["FMP_API_KEY"]

    _config_cache = cfg
    return cfg


def get(key_path: str, default: Any = None) -> Any:
    """
    Dot-notation access. e.g. get('guardrails.autonomous_trading_mode')
    """
    cfg = load_config()
    parts = key_path.split(".")
    node = cfg
    for part in parts:
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def is_autonomous_trading() -> bool:
    return bool(get("guardrails.autonomous_trading_mode", False))


def get_agent_model(agent_id: str) -> str:
    return get(f"agent_models.{agent_id}", "deepseek/deepseek-chat")


def get_alpaca_creds(agent_id: str) -> dict:
    agent_upper = agent_id.upper()
    # Prefer environment variables (set in Render dashboard, never in repo)
    api_key = (
        os.environ.get(f"ALPACA_KEY_{agent_upper}")
        or get(f"alpaca.{agent_id}.api_key", "")
    )
    api_secret = (
        os.environ.get(f"ALPACA_SECRET_{agent_upper}")
        or get(f"alpaca.{agent_id}.secret_key", "")
    )
    return {
        "api_key": api_key,
        "api_secret": api_secret,
        "base_url": "https://paper-api.alpaca.markets/v2",  # shared for all 7 accounts
    }


def get_hrv_config() -> dict:
    return get("hrv", {})


def get_runtime_config() -> dict:
    return get("runtime", {})


def get_guardrails() -> dict:
    return get("guardrails", {})
