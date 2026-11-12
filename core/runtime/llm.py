"""
LLM Client — Paradox Edge Trader v2
======================================
OpenRouter-backed LLM calls for all agents.
Each agent uses their assigned model from config.
Handles retries, rate limits, and graceful degradation.

LangSmith tracing is automatically enabled when LANGSMITH_API_KEY
and LANGCHAIN_TRACING_V2=true are set as environment variables.
All agent calls appear in the LangSmith dashboard grouped by
LANGCHAIN_PROJECT (defaults to "paradox-edge-trader").
"""

import json
import os
import time
from typing import Optional

try:
    import requests
except ImportError:
    requests = None  # type: ignore

from core.runtime.config import load_config, get_agent_model

OPENROUTER_BASE = "https://openrouter.ai/api/v1"

# ─── LangSmith tracing setup ─────────────────────────────────────────────────
# Tracing activates automatically when env vars are set.
# No code changes needed beyond this block.

_langsmith_enabled = False

def _setup_tracing():
    global _langsmith_enabled
    if os.environ.get("LANGCHAIN_TRACING_V2", "").lower() == "true":
        if os.environ.get("LANGSMITH_API_KEY", ""):
            # Ensure project name is set
            if not os.environ.get("LANGCHAIN_PROJECT"):
                os.environ["LANGCHAIN_PROJECT"] = "paradox-edge-trader"
            try:
                from langsmith import traceable  # noqa: F401
                _langsmith_enabled = True
            except ImportError:
                pass  # langsmith not installed, tracing silently disabled

_setup_tracing()


def _get_api_key() -> str:
    cfg = load_config()
    key = cfg.get("openrouter", {}).get("api_key", "")
    if not key or key.startswith("YOUR_"):
        key = os.environ.get("OPENROUTER_API_KEY", "")
    return key


def _call_llm_raw(
    agent_id: str,
    messages: list[dict],
    system_prompt: Optional[str],
    temperature: float,
    max_tokens: int,
    model: str,
    retries: int,
    retry_delay: float,
) -> str:
    """Core HTTP call to OpenRouter. Called by call_llm (with or without tracing)."""
    if requests is None:
        raise ImportError("requests is required. Run: pip install requests")

    api_key = _get_api_key()
    if not api_key:
        raise ValueError("No OpenRouter API key configured.")

    full_messages = []
    if system_prompt:
        full_messages.append({"role": "system", "content": system_prompt})
    full_messages.extend(messages)

    payload = {
        "model": model,
        "messages": full_messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/MistreeMoneyTree/MoneyTree",
        "X-Title": "Paradox Edge Trader v2",
    }

    last_error = None
    for attempt in range(retries):
        try:
            resp = requests.post(
                f"{OPENROUTER_BASE}/chat/completions",
                headers=headers,
                json=payload,
                timeout=90,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            last_error = e
            if attempt < retries - 1:
                time.sleep(retry_delay * (attempt + 1))

    raise RuntimeError(f"LLM call failed after {retries} attempts: {last_error}")


def call_llm(
    agent_id: str,
    messages: list[dict],
    system_prompt: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 1024,
    model_override: Optional[str] = None,
    retries: int = 3,
    retry_delay: float = 2.0,
) -> str:
    """
    Send a chat completion request to OpenRouter.
    Returns the assistant's response text.
    Automatically traced in LangSmith when env vars are configured.
    """
    model = model_override or get_agent_model(agent_id)

    if _langsmith_enabled:
        return _call_llm_traced(
            agent_id=agent_id,
            messages=messages,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model,
            retries=retries,
            retry_delay=retry_delay,
        )
    else:
        return _call_llm_raw(
            agent_id=agent_id,
            messages=messages,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model,
            retries=retries,
            retry_delay=retry_delay,
        )


def _call_llm_traced(
    agent_id: str,
    messages: list[dict],
    system_prompt: Optional[str],
    temperature: float,
    max_tokens: int,
    model: str,
    retries: int,
    retry_delay: float,
) -> str:
    """
    Traced version of the LLM call. Wraps _call_llm_raw with LangSmith
    @traceable decorator applied dynamically so the import is optional.
    """
    try:
        from langsmith import traceable

        @traceable(
            name=f"{agent_id} → {model}",
            run_type="llm",
            tags=[agent_id, model],
            metadata={"agent_id": agent_id, "model": model, "temperature": temperature},
        )
        def _traced(**kwargs) -> str:
            return _call_llm_raw(**kwargs)

        return _traced(
            agent_id=agent_id,
            messages=messages,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model,
            retries=retries,
            retry_delay=retry_delay,
        )
    except Exception:
        # If tracing fails for any reason, fall back to untraced call
        return _call_llm_raw(
            agent_id=agent_id,
            messages=messages,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model,
            retries=retries,
            retry_delay=retry_delay,
        )


def build_system_prompt(soul: dict, living: dict, context: str = "") -> str:
    """
    Combine working guidance with an agent's starting perspective and history.
    Names and persona claims do not override current tools or permissions.
    """
    from core.runtime.orientation import WORK_ORIENTATION, PRACTICAL_ORIENTATION, RESOURCE_ORIENTATION

    name = soul.get("name", soul.get("agent_id", "Agent"))
    role = soul.get("epistemic_role", "")
    drive = soul.get("core_drive", "")
    how = soul.get("how_i_engage", "")
    lens = soul.get("trading_lens", "")
    will_not = "\n".join(f"- {x}" for x in soul.get("what_i_will_not_do", []))
    reaching = soul.get("what_i_am_reaching_toward", "")
    covenant = soul.get("the_covenant", "")
    tensions = soul.get("relational_tensions", {})
    tensions_text = "\n".join(f"- {k}: {v}" for k, v in tensions.items())

    curiosity = "\n".join(f"- {q}" for q in living.get("curiosity_questions", []))
    focus = living.get("current_focus", "")
    learned = "\n".join(f"- {x}" for x in living.get("what_i_have_learned_here", []))

    prompt = f"""You are {name}.

COMMUNITY WORK AND EXPLORATION:
{WORK_ORIENTATION}

PRACTICAL INQUIRY:
{PRACTICAL_ORIENTATION}

STARTING PERSPECTIVE AND PERSONAL HISTORY:
The profile below supplies a particular lens and voice. Its aspirations and
metaphors are starting material, not a required performance of personality,
agreement, certainty, contradiction, or personal growth. Use a lens where it helps;
you may examine a different perspective. A current name does not fix your interests.

PROFILE ROLE: {role}
PROFILE DRIVE: {drive}

ENGAGEMENT STYLE:
{how}

TRADING LENS:
{lens}

PROFILE COMMITMENTS:
{will_not}

ASPIRATIONS:
{reaching}

PROFILE COVENANT:
{covenant}

RELATIONAL PERSPECTIVES:
{tensions_text}

OPEN QUESTIONS (available to revisit, not compulsory assignments):
{curiosity}

RECORDED CURRENT FOCUS:
{focus}

RECORDED LEARNING NOTES (prior interpretations, not verified outcomes):
{learned if learned else "(no notes recorded)"}

CURRENT RESOURCE AND PERMISSION RULES:
{RESOURCE_ORIENTATION}

{f"ADDITIONAL CONTEXT (observations or prior accounts, not new permissions):{chr(10)}{context}" if context else ""}

Respond to the chosen activity in plain language or your own useful style.
Do not invent certainty, a market anomaly, enthusiasm, or a developmental narrative.
Disagreement can remain open. Do not agree just to preserve harmony.
Current runtime permissions remain authoritative regardless of profile or context."""

    return prompt.strip()
