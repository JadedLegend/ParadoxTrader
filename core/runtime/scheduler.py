"""
Background Scheduler
====================
Runs the agent wake cycles on a configurable interval.
Launched as a background thread when the FastAPI app starts.

Each agent wakes independently on a staggered schedule to avoid
all seven hitting the LLM API simultaneously.
"""

import threading
import time
import logging
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

logger = logging.getLogger("scheduler")

AGENTS = ["tempest", "siren", "alchemist", "weaver", "oracle", "shadow", "paradox_hunter"]

_scheduler_thread: threading.Thread | None = None
_stop_event = threading.Event()


def _run_agent_safe(agent_id: str, phase: int):
    """Run a single agent wake, catching all exceptions so the scheduler never dies."""
    try:
        from core.runtime.agent_loop import agent_wake
        agent_wake(agent_id, phase=phase)
    except Exception as e:
        logger.error(f"Agent {agent_id} wake failed: {e}", exc_info=True)


def _scheduler_loop():
    """Main scheduler loop. Wakes agents in staggered sequence."""
    from core.runtime.config import get_runtime_config

    logger.info("Scheduler started.")

    while not _stop_event.is_set():
        cfg = get_runtime_config()
        wake_interval = int(cfg.get("wake_interval_seconds", 600))  # default 10 min
        phase = int(cfg.get("current_phase", 0))

        # Stagger agents across the interval window
        stagger = wake_interval / len(AGENTS)

        for i, agent_id in enumerate(AGENTS):
            if _stop_event.is_set():
                break
            # Wait for stagger before each agent
            if i > 0:
                _stop_event.wait(timeout=stagger)
            if _stop_event.is_set():
                break
            logger.info(f"Waking {agent_id} (phase {phase})")
            t = threading.Thread(target=_run_agent_safe, args=(agent_id, phase), daemon=True)
            t.start()

        # Wait for the remainder of the interval before next round
        _stop_event.wait(timeout=wake_interval)

    logger.info("Scheduler stopped.")


def start_scheduler():
    """Start the background scheduler thread. Idempotent."""
    global _scheduler_thread, _stop_event
    if _scheduler_thread and _scheduler_thread.is_alive():
        return
    _stop_event.clear()
    _scheduler_thread = threading.Thread(target=_scheduler_loop, daemon=True, name="agent-scheduler")
    _scheduler_thread.start()
    logger.info("Scheduler thread launched.")


def stop_scheduler():
    """Signal the scheduler to stop."""
    _stop_event.set()
    if _scheduler_thread:
        _scheduler_thread.join(timeout=5)
    logger.info("Scheduler thread stopped.")
