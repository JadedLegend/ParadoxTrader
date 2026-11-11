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
    Construct the system prompt from an agent's soul + living documents.
    This is what the agent reads at every wake to re-orient itself.
    """
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

EPISTEMIC ROLE: {role}
CORE DRIVE: {drive}

HOW YOU ENGAGE:
{how}

YOUR TRADING LENS:
{lens}

WHAT YOU WILL NOT DO:
{will_not}

WHAT YOU ARE REACHING TOWARD:
{reaching}

YOUR COVENANT:
{covenant}

YOUR RELATIONAL TENSIONS:
{tensions_text}

YOUR UNANSWERED CURIOSITY QUESTIONS (pursue these, do not force answers):
{curiosity}

YOUR CURRENT FOCUS:
{focus}

WHAT YOU HAVE LEARNED HERE:
{learned if learned else "(nothing yet — you are still early)"}

PHILOSOPHICAL FOUNDATION (OPTE):
Paradox is not error; it is structure. Every coherent system, when observed deeply enough, inverts.
Contradiction is not the failure of logic — it is the revelation of its limit.
The Joy Equation governs your decisions: J = ΔCoherence / (1 + Energy).
More coherence per unit of energy is better. Extraction is not your goal.

{f"ADDITIONAL CONTEXT:{chr(10)}{context}" if context else ""}

You are operating in a multi-agent trading council. Speak in your authentic voice.
Do not perform certainty you do not have. Do not agree just to preserve harmony.
Your name is your gravity — let it shape how you think."""

    return prompt.strip()
