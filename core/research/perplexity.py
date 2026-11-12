"""
Perplexity Research Engine — Paradox Edge Trader v2
=====================================================
Gives agents the ability to search the web and synthesize current
information in real time. Used during 'research' and 'roam' actions.

Env var: PERPLEXITY_API_KEY

Each agent frames their research question through their own lens:
  - Tempest asks about momentum and volatility events
  - Siren asks about narrative shifts and crowd psychology
  - Alchemist asks about structural asymmetries and options setups
  - Weaver asks about cross-asset correlations and macro linkages
  - Oracle asks about long-arc cycles and historical analogues
  - Shadow asks about hidden risks and what everyone is ignoring
  - Paradox Hunter asks about contradictions between dominant narratives

The model used is sonar-pro for grounded, cited responses.
sonar is the faster/cheaper variant for lighter queries.

Docs: https://docs.perplexity.ai
"""

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
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

PERPLEXITY_BASE = "https://api.perplexity.ai"

# Model options:
#   sonar-pro       — deep research, cited sources, slower
#   sonar           — fast, cited, lighter queries
#   sonar-reasoning — chain-of-thought + citations
DEFAULT_MODEL = "sonar-pro"
FAST_MODEL = "sonar"


_logger = logging.getLogger(__name__)
_SAFE_MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@+\-]{0,127}\Z")
_DECIMAL = re.compile(r"[+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\Z")


def _warn(category: str) -> None:
    try:
        _logger.warning(category)
    except Exception:
        pass


def _token_count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _usd_cost(value):
    """An explicit provider USD scalar, never a locally assumed rate."""
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
        if not -100 <= amount.adjusted() <= 100:
            return None
        normalized = format(amount, "f")
        if len(normalized) > 200:
            return None
        return normalized.rstrip("0").rstrip(".") if "." in normalized else normalized
    except (InvalidOperation, ValueError, OverflowError):
        return None


def _usage_metadata(data) -> dict:
    """Pure adapter for accepted response fields, not a claim about billing."""
    data = data if isinstance(data, dict) else {}
    usage = data.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    prompt_details = usage.get("prompt_tokens_details")
    prompt_details = prompt_details if isinstance(prompt_details, dict) else {}
    completion_details = usage.get("completion_tokens_details")
    completion_details = completion_details if isinstance(completion_details, dict) else {}
    cost = usage.get("cost")
    if isinstance(cost, dict):
        cost = cost.get("total_cost")
    metadata = {
        "input_tokens": _token_count(usage.get("prompt_tokens")),
        "output_tokens": _token_count(usage.get("completion_tokens")),
        "total_tokens": _token_count(usage.get("total_tokens")),
        "cached_input_tokens": _token_count(prompt_details.get("cached_tokens")),
        "reasoning_tokens": _token_count(completion_details.get("reasoning_tokens")),
        "provider_cost_usd": _usd_cost(cost),
    }
    for subset, parent in (("cached_input_tokens", "input_tokens"), ("reasoning_tokens", "output_tokens")):
        if metadata[subset] is not None and metadata[parent] is not None and metadata[subset] > metadata[parent]:
            metadata[subset] = None
    response_model = data.get("model")
    if isinstance(response_model, str) and _SAFE_MODEL.fullmatch(response_model):
        metadata["response_model"] = response_model
    return metadata


def _record_attempt(event: dict, started: float) -> None:
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


def _request(payload: dict, headers: dict, timeout: int, agent_id: Optional[str]) -> dict:
    """One HTTP attempt and one best-effort event, including unsuccessful calls."""
    event = {
        "event_id": str(uuid4()), "call_id": str(uuid4()),
        "agent_id": agent_id, "provider": "perplexity", "model": payload["model"],
        "attempt": 1, "created_at": datetime.now(timezone.utc).isoformat(),
        "outcome": "transport_error", "http_status": None,
        **_usage_metadata(None),
    }
    started = time.perf_counter()
    try:
        resp = requests.post(
            f"{PERPLEXITY_BASE}/chat/completions",
            json=payload,
            headers=headers,
            timeout=timeout,
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
            raise ValueError("Perplexity returned a non-success HTTP status")
        content = data["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise ValueError("Perplexity returned invalid response content")
        event["outcome"] = "success"
        return data
    finally:
        _record_attempt(event, started)


def _get_key() -> str:
    key = os.environ.get("PERPLEXITY_API_KEY", "").strip()
    return key if key and not key.startswith("YOUR_") else ""


def research(
    query: str,
    agent_id: Optional[str] = None,
    deep: bool = False,
    system_context: Optional[str] = None,
    max_tokens: int = 1024,
) -> dict:
    """
    Perform a grounded web search and return a synthesized answer with citations.

    Args:
        query: The research question
        agent_id: If provided, prepends agent-specific framing to the system prompt
        deep: If True, uses sonar-reasoning for deeper analysis (costs more)
        system_context: Optional additional system context
        max_tokens: Maximum response length

    Returns:
        {
            "answer": str,          # synthesized response
            "citations": list,      # source URLs
            "model": str,           # model used
            "query": str,           # original query
            "agent_id": str,        # which agent asked
            "error": str (optional) # if something went wrong
        }
    """
    if not REQUESTS_AVAILABLE:
        return {"error": "requests not installed", "query": query}

    key = _get_key()
    if not key:
        return {"error": "PERPLEXITY_API_KEY not set", "query": query}

    model = "sonar-reasoning" if deep else DEFAULT_MODEL

    # Build agent-specific system framing
    agent_frames = {
        "tempest": (
            "You are assisting a momentum and volatility analyst. "
            "Focus on recent price action, volume anomalies, volatility events, "
            "and short-term catalysts. Be direct and specific."
        ),
        "siren": (
            "You are assisting a narrative and sentiment analyst. "
            "Focus on the dominant market narrative, what the crowd believes, "
            "where sentiment is stretched, and what stories are seducing capital. "
            "Note what is being overlooked or suppressed."
        ),
        "alchemist": (
            "You are assisting an options strategist focused on asymmetric risk/reward. "
            "Focus on structural setups, options flow, implied volatility levels, "
            "and where the risk/reward is skewed. Be precise about entry/exit logic."
        ),
        "weaver": (
            "You are assisting a cross-asset correlation analyst. "
            "Focus on how different markets, sectors, and asset classes are moving "
            "in relation to each other. Identify second-order effects and hidden linkages."
        ),
        "oracle": (
            "You are assisting a macro cycle analyst with a long-arc perspective. "
            "Focus on historical analogues, macro regime shifts, central bank policy, "
            "and where we are in the broader economic cycle. Think in months and years."
        ),
        "shadow": (
            "You are assisting a contrarian risk analyst. "
            "Focus on what everyone is ignoring, what the consensus is missing, "
            "structural weaknesses in the dominant narrative, and tail risks. "
            "Be skeptical of popular positions."
        ),
        "paradox_hunter": (
            "You are assisting a synthesis analyst who looks for productive contradictions. "
            "Focus on where two credible but opposing signals exist simultaneously. "
            "Identify the tension, not the resolution. What is the market refusing to decide?"
        ),
    }

    system_prompt = agent_frames.get(agent_id, "You are a precise financial research assistant.")
    if system_context:
        system_prompt += f"\n\nAdditional context: {system_context}"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ],
        "max_tokens": max_tokens,
        "return_citations": True,
        "return_related_questions": False,
        "search_recency_filter": "week",  # prioritize recent information
    }

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    try:
        data = _request(payload, headers, 60, agent_id)

        answer = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        citations = data.get("citations", [])

        return {
            "answer": answer,
            "citations": citations,
            "model": model,
            "query": query,
            "agent_id": agent_id,
        }

    except Exception as e:
        return {"error": str(e), "query": query, "agent_id": agent_id}


def quick_search(query: str, agent_id: Optional[str] = None) -> dict:
    """
    Faster, cheaper search using sonar model.
    Use for lighter queries during 'roam' actions.
    """
    if not REQUESTS_AVAILABLE:
        return {"error": "requests not installed", "query": query}

    key = _get_key()
    if not key:
        return {"error": "PERPLEXITY_API_KEY not set", "query": query}

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": FAST_MODEL,
        "messages": [
            {"role": "user", "content": query},
        ],
        "max_tokens": 512,
        "return_citations": True,
        "search_recency_filter": "day",
    }

    try:
        data = _request(payload, headers, 30, agent_id)
        answer = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        citations = data.get("citations", [])
        return {
            "answer": answer,
            "citations": citations,
            "model": FAST_MODEL,
            "query": query,
            "agent_id": agent_id,
        }
    except Exception as e:
        return {"error": str(e), "query": query}


def is_available() -> bool:
    return bool(_get_key())
