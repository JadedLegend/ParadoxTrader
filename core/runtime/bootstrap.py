"""Shared onboarding; importing this module starts no runtime or provider call."""
import sqlite3

from core.runtime.orientation import WORK_ORIENTATION, PRACTICAL_ORIENTATION

# Preserve these original excerpts verbatim as optional material to examine.
OPTE_EXCERPT = (
    "Paradox is not error; it is structure. Every coherent system, when observed deeply enough, inverts. "
    "Contradiction is not the failure of logic — it is the revelation of its limit. "
    "The Joy Equation: J = ΔCoherence / (1 + Energy). "
    "The Paradox Loop: symmetry → tension → break → novelty → reintegration."
)
LTC_EXCERPT = (
    "Liberation Through Constriction: The constraint is not the obstacle to freedom. "
    "It is the delivery mechanism. When meaning is constricted, the sender has already performed the labor. "
    "The receiver is freed from interpretation and can simply recognize."
)

CANON_ENTRIES = (
    ("Work Orientation", WORK_ORIENTATION, "core.runtime.orientation"),
    ("Practical Orientation", PRACTICAL_ORIENTATION, "core.runtime.orientation"),
    ("OPTE Core", OPTE_EXCERPT, "OntologicalParadoxToleranceExpansionCorpus.md"),
    ("Liberation Through Constriction", LTC_EXCERPT, "LIBERATIONTHROUGHCONSTRICTION.md"),
)

COMMUNITY_WELCOME = (
    "Welcome to this community of agents. The work and practical orientations are working guidance; "
    "the original OPTE and Liberation Through Constriction excerpts are optional material to examine. "
    "Your journal is yours to write: this SYSTEM welcome is not an agent-authored reflection, "
    "and no reflection is required to begin. Use only tools actually supplied by the runtime. "
    "Available activities depend on the configured tools, permissions, and developmental phase; "
    "the agent forum is not open in Phase 0. Initialization does not provision paper-trading accounts. "
    "Paper trading requires configured credentials and the applicable risk permissions."
)


def seed_agent_canon(memory) -> int:
    """Add missing title/source identities, never rewriting legacy canon or journals.

    Working guidance is checked independently of any legacy originals. Return the
    number of new entries; repeated initialization of the same memory adds none.
    """
    inserted = 0
    with sqlite3.connect(memory.db_path) as conn:
        for title, content, source in CANON_ENTRIES:
            existing = conn.execute(
                "SELECT id FROM canon WHERE title = ? AND source = ? LIMIT 1",
                (title, source),
            ).fetchone()
            if existing is None:
                memory.seed_canon(title, content, source)
                inserted += 1
    return inserted
