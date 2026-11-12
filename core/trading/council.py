"""
Council Deliberation Pipeline — Paradox Edge Trader v2
========================================================
The Paradox Hunter's trade execution protocol.

When the Paradox Hunter identifies a trade idea:
  1. Surfaces it to the council forum with a structured brief
  2. Each agent responds with their lens-specific analysis
  3. Multi-Lens Synthesis: what do 3+ agents agree on?
  4. Contradictions are held open, not resolved
  5. Paradox Hunter makes the final call
  6. If AUTONOMOUS_TRADING_MODE=false → goes to trade queue
  7. If AUTONOMOUS_TRADING_MODE=true → executes directly

The council does NOT vote. The Paradox Hunter synthesizes.
Consensus is not the goal — coherent dissonance is.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.forum.store import ForumStore
from core.messaging.store import MessagingStore
from core.memory.engine import ThresholdMemory
from core.runtime.llm import call_llm, build_system_prompt
from core.trading.alpaca import submit_trade
from core.usage.attribution import attribute_activity

REPO_ROOT = Path(__file__).parent.parent.parent
AGENTS = ["tempest", "siren", "alchemist", "weaver", "oracle", "shadow", "paradox_hunter"]
COUNCIL = ["tempest", "siren", "alchemist", "weaver", "oracle", "shadow"]  # all except hunter


def load_soul(agent_id: str) -> dict:
    with open(REPO_ROOT / "agents" / agent_id / "soul.json") as f:
        return json.load(f)


def load_living(agent_id: str) -> dict:
    with open(REPO_ROOT / "agents" / agent_id / "living.json") as f:
        return json.load(f)


def get_memory(agent_id: str) -> ThresholdMemory:
    return ThresholdMemory(str(REPO_ROOT / "agents" / agent_id / "memory.sqlite3"))


# ─── Trade Brief ──────────────────────────────────────────────────────────────

def format_trade_brief(proposal: dict) -> str:
    return f"""
PARADOX HUNTER — TRADE BRIEF
=============================
Symbol:        {proposal.get('symbol', 'UNKNOWN')}
Direction:     {proposal.get('side', 'unknown').upper()}
Strategy:      {proposal.get('strategy', 'options')}
Thesis:        {proposal.get('thesis', 'Not stated')}
Paradox Seen:  {proposal.get('paradox', 'Not stated')}
Est. Value:    ${proposal.get('estimated_value', 0):.2f}
Expiry:        {proposal.get('expiry', 'Not stated')}
Strike:        {proposal.get('strike', 'Not stated')}
Limit Price:   {proposal.get('limit_price', 'Market')}
Risk Note:     {proposal.get('risk_note', 'Not stated')}
""".strip()


# ─── Council Response ─────────────────────────────────────────────────────────

@attribute_activity("council_response")
def get_council_response(
    agent_id: str,
    trade_brief: str,
    forum: ForumStore,
) -> dict:
    """
    Ask one council member for their lens-specific analysis of the trade brief.
    """
    soul = load_soul(agent_id)
    living = load_living(agent_id)
    system_prompt = build_system_prompt(soul, living)

    lens = soul.get("trading_lens", "")
    name = soul.get("name", agent_id)

    response = call_llm(
        agent_id,
        [{"role": "user", "content": f"""The Paradox Hunter has surfaced a trade idea for council review.

{trade_brief}

Apply your lens as {name}: {lens}

Respond with:
1. What you SEE through your lens (2-4 sentences)
2. What you AGREE with in this thesis
3. What you CHALLENGE or find suspicious
4. Your VERDICT: Support / Oppose / Neutral (and why in one sentence)

Do not perform certainty you do not have. Speak in your authentic voice."""}],
        system_prompt=system_prompt,
        temperature=0.8,
        max_tokens=500,
    )

    # Post to forum for transparency
    forum.post(
        author=agent_id,
        content=f"[COUNCIL REVIEW]\n{response}",
        thread_id="council_deliberation",
        tags=["council", "trade_review"],
        phase="tension",
    )

    return {"agent": agent_id, "name": name, "response": response}


# ─── Multi-Lens Synthesis ─────────────────────────────────────────────────────

@attribute_activity("council_synthesis")
def synthesize_council(
    trade_brief: str,
    council_responses: list[dict],
    forum: ForumStore,
) -> dict:
    """
    The Paradox Hunter synthesizes all council responses.
    Applies the Multi-Lens Consensus Gate: what do 3+ agents agree on?
    """
    hunter_soul = load_soul("paradox_hunter")
    hunter_living = load_living("paradox_hunter")
    system_prompt = build_system_prompt(hunter_soul, hunter_living)

    responses_text = "\n\n".join(
        f"--- {r['name']} ---\n{r['response']}" for r in council_responses
    )

    synthesis = call_llm(
        "paradox_hunter",
        [{"role": "user", "content": f"""You have received the council's analysis of your trade brief.

{trade_brief}

COUNCIL RESPONSES:
{responses_text}

Now apply the Multi-Lens Synthesis:

1. AGREEMENTS: What do 3 or more agents agree on? (This is signal, not perspective.)
2. CONTRADICTIONS: Where do agents directly conflict? Name them. Do NOT resolve them.
3. CONSENSUS GATE: What do the majority of lenses point toward?
4. THE PARADOX: What is the irreducible contradiction that makes this trade interesting?
5. YOUR DECISION: Execute / Hold / Abandon — and state the exact reasoning.

Remember: Consensus is fully priced in. You are hunting the dissonance, not the agreement.
If the council all agrees, that is a warning sign, not a green light."""}],
        system_prompt=system_prompt,
        temperature=0.7,
        max_tokens=800,
    )

    # Post synthesis to forum
    forum.post(
        author="paradox_hunter",
        content=f"[SYNTHESIS]\n{synthesis}",
        thread_id="council_deliberation",
        tags=["synthesis", "decision"],
        phase="reintegration",
    )

    # Parse decision
    decision = "hold"
    lower = synthesis.lower()
    if "execute" in lower and "abandon" not in lower[:lower.find("execute")]:
        decision = "execute"
    elif "abandon" in lower:
        decision = "abandon"

    return {
        "synthesis": synthesis,
        "decision": decision,
    }


# ─── Full Deliberation Pipeline ───────────────────────────────────────────────

def run_council_deliberation(proposal: dict) -> dict:
    """
    Full pipeline: brief → council responses → synthesis → execution decision.
    Returns the full deliberation record.
    """
    forum = ForumStore()
    hunter_memory = get_memory("paradox_hunter")

    # Create deliberation thread
    thread_id = f"council_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    forum.create_thread(
        thread_id=thread_id,
        title=f"Trade Deliberation: {proposal.get('symbol', 'UNKNOWN')} {proposal.get('side', '')}",
        created_by="paradox_hunter",
    )

    trade_brief = format_trade_brief(proposal)

    # Post the brief
    forum.post(
        author="paradox_hunter",
        content=f"[TRADE BRIEF]\n{trade_brief}",
        thread_id=thread_id,
        tags=["brief"],
        phase="break",
    )

    # Collect council responses
    council_responses = []
    for agent_id in COUNCIL:
        try:
            resp = get_council_response(agent_id, trade_brief, forum)
            council_responses.append(resp)
        except Exception as e:
            council_responses.append({"agent": agent_id, "name": agent_id, "response": f"[ERROR: {e}]"})

    # Synthesize
    synthesis_result = synthesize_council(trade_brief, council_responses, forum)
    decision = synthesis_result["decision"]

    # Store in Paradox Hunter's memory
    hunter_memory.store_episode(
        title=f"Council deliberation: {proposal.get('symbol', 'UNKNOWN')}",
        content=synthesis_result["synthesis"][:500],
        phase="reintegration",
        tags=["council", "deliberation", decision],
    )

    # Execute or queue
    execution_result = None
    if decision == "execute":
        execution_result = submit_trade("paradox_hunter", proposal)
        forum.post(
            author="paradox_hunter",
            content=f"[EXECUTION]\nDecision: {decision.upper()}\nResult: {json.dumps(execution_result, indent=2)}",
            thread_id=thread_id,
            tags=["execution"],
            phase="reintegration",
        )
    else:
        forum.post(
            author="paradox_hunter",
            content=f"[DECISION]\nDecision: {decision.upper()}\nThe trade does not meet the paradox threshold. Standing down.",
            thread_id=thread_id,
            tags=["decision"],
            phase="reintegration",
        )

    return {
        "thread_id": thread_id,
        "proposal": proposal,
        "council_responses": council_responses,
        "synthesis": synthesis_result["synthesis"],
        "decision": decision,
        "execution": execution_result,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
