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

import os
from typing import Optional

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

PERPLEXITY_BASE = "https://api.perplexity.ai"

# Model options:
#   sonar-pro       — deep research, cited sources, slower (~$3/1M tokens)
#   sonar           — fast, cited, lighter queries (~$1/1M tokens)
#   sonar-reasoning — chain-of-thought + citations (~$5/1M tokens)
DEFAULT_MODEL = "sonar-pro"
FAST_MODEL = "sonar"


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
        resp = requests.post(
            f"{PERPLEXITY_BASE}/chat/completions",
            json=payload,
            headers=headers,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()

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
        resp = requests.post(
            f"{PERPLEXITY_BASE}/chat/completions",
            json=payload,
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
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
