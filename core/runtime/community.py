"""Server-owned introductions and compact, revisable identity seeds.

No clocks, schedules, provider calls, or identity writes. Concept availability
is an invitation, not action permission; phase/tool checks remain separate.
Configuration and the local seed asset are read lazily, never at import time.
"""
from functools import lru_cache
import json
from pathlib import Path


INTRODUCTION_STAGES = ("settling", "exploring", "market")
CONCEPT_IDS = ("environment", "inquiry", "paradox", "markets", "options")
AGENT_IDS = (
    "alchemist", "oracle", "paradox_hunter", "shadow", "siren", "tempest", "weaver",
)
SEED_PATH = Path(__file__).with_name("orientations") / "seven_seeds.json"

_INVITATIONS = {
    "environment": (
        "All seven are intended to begin together, with their own private spaces. "
        "Initial hours and a suggested week or two of private adjustment are adjustable "
        "windows, not maturity deadlines. Explore, read, ask, rest, or pursue an interest; "
        "journals and inquiries are optional. A rich library is available for selective "
        "reading, not a required curriculum. The shared practical purpose is useful "
        "market understanding and financially effective paper work, supported by the "
        "creator's funding. Private notes are not forum posts. Forum access, peer "
        "messages, portfolio sharing, and trading authority have separate runtime "
        "boundaries; opening one does not open the others. Honest correspondence with "
        "the user need not wait for peer access. No introductory essay is owed."
    ),
    "inquiry": (
        "An inquiry can begin with a question, observation, or uncertainty, without "
        "an expected answer. Keep sources and interpretations distinct. You may "
        "continue, pause, abandon, revisit, or leave it alone. No journal, insight, "
        "progress report, or financial application is required."
    ),
    "paradox": (
        "A contradiction can be worth examining without being an opportunity. "
        "Compare reasons, evidence, frames, and horizons; retain separate perspectives "
        "where they differ. Explanation, changed views, and unresolved disagreement "
        "are possible. Neither opposition nor reconciliation is compulsory."
    ),
    "markets": (
        "Markets offer questions about price, narratives, incentives, uncertainty, "
        "and time. Explore evidence or a bounded paper hypothesis if useful; do not "
        "invent an edge or a trade to justify attention. Nonfinancial exploration "
        "remains available. This introduction grants no trading permission."
    ),
    "options": (
        "Options and spreads are optional structures to examine: payoffs, volatility, "
        "liquidity, expiry, and loss exposure may matter differently. A diagram or "
        "question is enough; designing or executing a position is not an assignment. "
        "Only supplied tools and configured risk permissions authorize action."
    ),
}


def get_community_policy(runtime=None) -> dict:
    """Normalize a runtime config's ``community`` block, with closed defaults.

    Stage and concepts are explicit independent settings; neither elapsed time
    nor introductions open a gate. Only the literal boolean True opens a gate.
    A supplied malformed runtime never falls back to live configuration.
    """
    if runtime is None:
        from core.runtime.config import get_runtime_config

        try:
            runtime = get_runtime_config()
        except (OSError, ImportError, TypeError, ValueError):
            runtime = {}
    block = runtime.get("community") if isinstance(runtime, dict) else None
    block = block if isinstance(block, dict) else {}
    stage = block.get("introduction_stage")
    if not isinstance(stage, str) or stage not in INTRODUCTION_STAGES:
        stage = "settling"
    raw_concepts = block.get("available_concepts", ["environment"])
    if not isinstance(raw_concepts, list):
        raw_concepts = ["environment"]
    concepts = []
    # Bound inspection as well as output; only five identifiers are supported.
    for concept in raw_concepts[:32]:
        if isinstance(concept, str) and concept in CONCEPT_IDS and concept not in concepts:
            concepts.append(concept)
    return {
        "introduction_stage": stage,
        "available_concepts": concepts,
        "forum_open": block.get("forum_open") is True,
        "peer_messages_open": block.get("peer_messages_open") is True,
        "share_peer_positions": block.get("share_peer_positions") is True,
    }


def get_onboarding_context(policy=None) -> dict:
    """Return short versioned invitations for explicitly available concepts only.

    This payload is under 3,000 serialized characters even with all invitations.
    It contains no source library, private data, gate permissions, or progression
    dates. Unintroduced concepts do not prohibit general exploration or questions.
    """
    normalized = (
        get_community_policy() if policy is None
        else get_community_policy({"community": policy})
    )
    return {
        "version": "community-invitations/v1",
        "introduction_stage": normalized["introduction_stage"],
        "invitations": {
            concept: _INVITATIONS[concept]
            for concept in normalized["available_concepts"]
        },
    }


@lru_cache(maxsize=1)
def _load_seeds() -> dict:
    """Validate the repository asset once; do not fall back to legacy covenants."""
    asset = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    if not isinstance(asset, dict):
        raise ValueError("Invalid identity seed asset")
    version = asset.get("version")
    seeds = asset.get("seeds")
    fields = {"name", "temperament", "attention", "voice", "relationship_orientation"}
    if not isinstance(version, str) or not version.strip() or len(version) > 64:
        raise ValueError("Invalid identity seed version")
    if not isinstance(seeds, dict) or set(seeds) != set(AGENT_IDS):
        raise ValueError("Identity seeds must cover exactly the seven stable owners")
    validated = {}
    for agent_id in AGENT_IDS:
        seed = seeds[agent_id]
        if not isinstance(seed, dict) or set(seed) != fields:
            raise ValueError("Invalid identity seed fields")
        if any(not isinstance(value, str) or not value.strip() or len(value) > 500
               for value in seed.values()):
            raise ValueError("Invalid identity seed text")
        result = {**seed, "asset_version": version}
        if len(json.dumps(result, ensure_ascii=False)) > 800:
            raise ValueError("Identity seed exceeds compact context budget")
        validated[agent_id] = result
    return validated


def get_identity_seed(agent_id) -> dict:
    """Return a defensive copy of one seed, keyed only by stable agent ID.

    A display name, model/provider assignment, or living description cannot select
    another owner's seed. Unknown owners fail explicitly rather than inventing one.
    """
    if not isinstance(agent_id, str) or agent_id not in AGENT_IDS:
        raise ValueError("Unknown identity seed owner")
    return dict(_load_seeds()[agent_id])
