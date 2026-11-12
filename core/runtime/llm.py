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
import logging
import math
import os
import re
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional
from uuid import uuid4

try:
    import requests
except ImportError:
    requests = None  # type: ignore

from core.runtime.config import load_config, get_agent_model

OPENROUTER_BASE = "https://openrouter.ai/api/v1"

_logger = logging.getLogger(__name__)
_SAFE_MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@+\-]{0,127}\Z")
_DECIMAL = re.compile(r"[+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\Z")


def _warn(category: str) -> None:
    """Bounded metadata-only warnings must not interrupt a provider operation."""
    try:
        _logger.warning(category)
    except Exception:
        pass


def _token_count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _usd_cost(value):
    """Normalize only an explicit provider USD scalar; unknown is not zero."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        return None
    try:
        text = str(value)
        if len(text) > 128 or not _DECIMAL.fullmatch(text):
            return None
        amount = Decimal(text)
        if not amount.is_finite() or amount < 0:
            return None
        if not amount:
            return "0"
        # Keep malformed/extreme values bounded without Decimal context rounding.
        if not -100 <= amount.adjusted() <= 100:
            return None
        normalized = format(amount, "f")
        if len(normalized) > 200:
            return None
        return normalized.rstrip("0").rstrip(".") if "." in normalized else normalized
    except (InvalidOperation, ValueError, OverflowError):
        return None


def _usage_metadata(data) -> dict:
    """Pure allowlist conversion of response usage, never retain response bodies."""
    data = data if isinstance(data, dict) else {}
    usage = data.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    prompt_details = usage.get("prompt_tokens_details")
    prompt_details = prompt_details if isinstance(prompt_details, dict) else {}
    completion_details = usage.get("completion_tokens_details")
    completion_details = completion_details if isinstance(completion_details, dict) else {}
    metadata = {
        "input_tokens": _token_count(usage.get("prompt_tokens")),
        "output_tokens": _token_count(usage.get("completion_tokens")),
        "total_tokens": _token_count(usage.get("total_tokens")),
        "cached_input_tokens": _token_count(prompt_details.get("cached_tokens")),
        "reasoning_tokens": _token_count(completion_details.get("reasoning_tokens")),
        "provider_cost_usd": _usd_cost(usage.get("cost")),
    }
    for subset, parent in (("cached_input_tokens", "input_tokens"), ("reasoning_tokens", "output_tokens")):
        if metadata[subset] is not None and metadata[parent] is not None and metadata[subset] > metadata[parent]:
            metadata[subset] = None
    response_model = data.get("model")
    if isinstance(response_model, str) and _SAFE_MODEL.fullmatch(response_model):
        metadata["response_model"] = response_model
    return metadata


def _record_attempt(event: dict, started: float) -> None:
    """The ledger is best-effort and isolated from provider retry handling."""
    try:
        elapsed = (time.perf_counter() - started) * 1000
        event["duration_ms"] = max(0.0, elapsed) if math.isfinite(elapsed) else 0.0
        from core.usage.context import current_usage_context
        from core.usage import record_usage

        context = current_usage_context()
        event["activity"] = context.get("activity", "unattributed")
        event["wake_id"] = context.get("wake_id")
        if not record_usage(event):
            _warn("usage_recording_failed")
    except Exception:
        _warn("usage_recording_failed")


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

    call_id = str(uuid4())
    last_error = None
    for attempt in range(retries):
        event = {
            "event_id": str(uuid4()), "call_id": call_id,
            "agent_id": agent_id, "provider": "openrouter", "model": model,
            "attempt": attempt + 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "outcome": "transport_error", "http_status": None,
            **_usage_metadata(None),
        }
        started = time.perf_counter()
        try:
            resp = requests.post(
                f"{OPENROUTER_BASE}/chat/completions",
                headers=headers,
                json=payload,
                timeout=90,
            )
            status = resp.status_code
            if isinstance(status, int) and not isinstance(status, bool) and 100 <= status <= 599:
                event["http_status"] = status
            http_error = event["http_status"] is not None and not 200 <= status < 300
            event["outcome"] = "http_error" if http_error else "invalid_response"
            try:
                data = resp.json()
            except Exception:
                resp.raise_for_status()
                raise
            event.update(_usage_metadata(data))
            resp.raise_for_status()
            if http_error:
                raise ValueError("OpenRouter returned a non-success HTTP status")
            content = data["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise ValueError("OpenRouter returned invalid response content")
            event["outcome"] = "success"
            return content
        except Exception as e:
            last_error = e
        finally:
            _record_attempt(event, started)
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
    kwargs = dict(
        agent_id=agent_id, messages=messages, system_prompt=system_prompt,
        temperature=temperature, max_tokens=max_tokens, model=model,
        retries=retries, retry_delay=retry_delay,
    )
    entered = False
    completed = None
    provider_error = None
    try:
        from langsmith import traceable

        @traceable(
            name=f"{agent_id} → {model}",
            run_type="llm",
            tags=[agent_id, model],
            metadata={"agent_id": agent_id, "model": model, "temperature": temperature},
        )
        def _traced(**kwargs) -> str:
            nonlocal entered, completed, provider_error
            if entered:
                if provider_error is not None:
                    raise provider_error
                if completed is not None:
                    return completed
                raise RuntimeError("Tracing re-entered an unfinished provider call")
            entered = True
            try:
                completed = _call_llm_raw(**kwargs)
                return completed
            except Exception as error:
                provider_error = error
                raise

        result = _traced(**kwargs)
        # A wrapper must not replace or suppress the provider's actual result.
        if not entered:
            raise RuntimeError("Tracing returned before provider entry")
        if provider_error is not None:
            raise provider_error
        return completed if completed is not None else result
    except Exception:
        if provider_error is not None:
            raise provider_error
        _warn("llm_tracing_failed")
        if completed is not None:
            return completed
        if not entered:
            # Setup/decorator failure before entry is the only safe fallback.
            return _call_llm_raw(**kwargs)
        raise


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
