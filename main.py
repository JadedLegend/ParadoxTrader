"""
Paradox Edge Trader v2 — Main Orchestrator
============================================
Entry point for the system.

Usage:
    python main.py run              # Start all agents in their wake cycles
    python main.py wake <agent>     # Manually trigger one agent wake
    python main.py forum            # Print the latest forum posts
    python main.py inbox <agent>    # Print an agent's unread messages
    python main.py dm <from> <to> <message>  # Send a direct message
    python main.py status           # Print all agent HRV states
    python main.py queue            # Print the pending trade queue
    python main.py approve <id>     # Approve a queued trade
    python main.py reject <id>      # Reject a queued trade
    python main.py phase <0|1|2|3>  # Set the developmental phase
    python main.py countdown <ISO_DATE>  # Set Phase 2 convergence countdown
    python main.py snapshot         # Print current market snapshot
    python main.py init             # Seed OPTE canon into all agent memories
"""

import json
import sys
import time
import threading
from datetime import datetime, timezone
from pathlib import Path

# ─── Ensure repo root is in path ─────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

from core.hrv.engine import HRVStore
from core.forum.store import ForumStore
from core.messaging.store import MessagingStore
from core.trading.alpaca import TradeQueue
from core.runtime.config import get_runtime_config, load_config
from core.runtime.bootstrap import COMMUNITY_WELCOME, seed_agent_canon
from core.data_dir import db_path, agent_db_path
from data.feeds.free_feeds import get_market_snapshot

AGENTS = ["tempest", "siren", "alchemist", "weaver", "oracle", "shadow", "paradox_hunter"]
REPO_ROOT = Path(__file__).parent


def get_phase() -> int:
    cfg = get_runtime_config()
    return int(cfg.get("current_phase", 0))


# ─── Commands ─────────────────────────────────────────────────────────────────

def cmd_status():
    store = HRVStore(db_path("hrv.sqlite3"))
    states = store.get_all_states()
    if not states:
        print("No HRV states found. Run 'python main.py init' first.")
        return
    print(f"\n{'Agent':<20} {'HRV':>8} {'Max':>6} {'Interval':>10} {'Last Tick'}")
    print("-" * 70)
    for s in states:
        interval_str = "YES" if s.in_interval else "no"
        tick = s.last_tick_at[:19] if s.last_tick_at else "never"
        print(f"{s.agent_id:<20} {s.hrv:>8.1f} {s.max_hrv:>6.0f} {interval_str:>10} {tick}")
    print()


def cmd_forum(limit: int = 20):
    forum = ForumStore()
    posts = forum.get_recent(limit=limit)
    if not posts:
        print("Forum is empty.")
        return
    print(f"\n{'='*60}")
    print("  FORUM — Recent Posts")
    print(f"{'='*60}")
    for p in reversed(posts):
        ts = p["created_at"][:16]
        print(f"\n[{ts}] {p['author'].upper()} (thread: {p['thread_id']})")
        print(p["content"][:400])
        print("-" * 40)


def cmd_inbox(agent_id: str):
    messaging = MessagingStore()
    msgs = messaging.get_inbox(agent_id, limit=20)
    if not msgs:
        print(f"No messages for {agent_id}.")
        return
    print(f"\n{'='*60}")
    print(f"  INBOX — {agent_id}")
    print(f"{'='*60}")
    for m in msgs:
        read_str = "" if m["read"] else " [UNREAD]"
        ts = m["created_at"][:16]
        print(f"\n[{ts}] From: {m['sender']}{read_str}")
        print(m["content"])
        print("-" * 40)


def cmd_dm(sender: str, recipient: str, content: str):
    messaging = MessagingStore()
    mid = messaging.send(sender=sender, recipient=recipient, content=content)
    print(f"Message sent (id={mid}): {sender} → {recipient}")


def cmd_queue():
    queue = TradeQueue()
    pending = queue.get_pending()
    if not pending:
        print("No pending trades in queue.")
        return
    print(f"\n{'='*60}")
    print("  TRADE QUEUE — Pending")
    print(f"{'='*60}")
    for t in pending:
        print(f"\nID: {t['id']} | Agent: {t['agent_id']} | {t['created_at'][:16]}")
        print(json.dumps(t["proposal"], indent=2))
        print("-" * 40)


def cmd_approve(trade_id: int, notes: str = ""):
    queue = TradeQueue()
    queue.approve(trade_id, notes)
    print(f"Trade {trade_id} approved.")


def cmd_reject(trade_id: int, notes: str = ""):
    queue = TradeQueue()
    queue.reject(trade_id, notes)
    print(f"Trade {trade_id} rejected.")


def cmd_snapshot():
    snap = get_market_snapshot()
    print(f"\n{'='*50}")
    print("  MARKET SNAPSHOT")
    print(f"{'='*50}")
    for k, v in snap.items():
        print(f"  {k:<25} {v}")
    print()


def cmd_countdown(iso_date: str):
    forum = ForumStore()
    fid = forum.post_announcement(
        content=f"The council converges on {iso_date}. The countdown has begun.",
        author="SYSTEM",
        is_countdown=True,
        countdown_target=iso_date,
    )
    print(f"Countdown set to {iso_date} (announcement id={fid})")


def cmd_init():
    """Seed working guidance, optional originals, and missing HRV state."""
    from core.memory.engine import ThresholdMemory
    from core.hrv.engine import HRVStore

    hrv_store = HRVStore(db_path("hrv.sqlite3"))

    for agent_id in AGENTS:
        soul_path = REPO_ROOT / "agents" / agent_id / "soul.json"
        mem = ThresholdMemory(agent_db_path(agent_id))
        seed_agent_canon(mem)

        # Init HRV
        hrv_store.load(agent_id, soul_path=str(soul_path))
        print(f"  Initialized: {agent_id}")

    # Init forum with welcome post
    forum = ForumStore()
    forum.create_thread("general", "General Discussion", "SYSTEM")
    forum.post(
        author="SYSTEM",
        content=COMMUNITY_WELCOME,
        thread_id="general",
        phase="symmetry",
    )
    print("\nSystem initialized. SYSTEM welcome recorded.")


def cmd_wake(agent_id: str):
    from core.runtime.agent_loop import agent_wake
    phase = get_phase()
    print(f"Waking {agent_id} (phase {phase})...")
    result = agent_wake(agent_id, phase=phase)
    print(json.dumps(result, indent=2, default=str))


def cmd_run():
    """Start all agents in continuous wake cycles."""
    from core.runtime.agent_loop import agent_wake
    cfg = get_runtime_config()
    interval = int(cfg.get("wake_interval_seconds", 600))
    phase = get_phase()

    print(f"\nStarting Paradox Edge Trader v2")
    print(f"Phase: {phase} | Wake interval: {interval}s")
    print(f"Agents: {', '.join(AGENTS)}")
    print(f"Press Ctrl+C to stop.\n")

    def run_agent(agent_id: str):
        while True:
            try:
                result = agent_wake(agent_id, phase=phase)
                action = result.get("action", "unknown")
                hrv = result.get("hrv", "?")
                print(f"[{datetime.now().strftime('%H:%M:%S')}] {agent_id}: {action} (HRV: {hrv})")
            except Exception as e:
                print(f"[ERROR] {agent_id}: {e}")
            time.sleep(interval)

    threads = []
    for agent_id in AGENTS:
        t = threading.Thread(target=run_agent, args=(agent_id,), daemon=True)
        t.start()
        threads.append(t)
        time.sleep(2)  # Stagger starts

    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("\nShutting down.")


# ─── CLI Dispatch ─────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return

    cmd = args[0]

    if cmd == "run":
        cmd_run()
    elif cmd == "wake" and len(args) >= 2:
        cmd_wake(args[1])
    elif cmd == "forum":
        cmd_forum()
    elif cmd == "inbox" and len(args) >= 2:
        cmd_inbox(args[1])
    elif cmd == "dm" and len(args) >= 4:
        cmd_dm(args[1], args[2], " ".join(args[3:]))
    elif cmd == "status":
        cmd_status()
    elif cmd == "queue":
        cmd_queue()
    elif cmd == "approve" and len(args) >= 2:
        cmd_approve(int(args[1]), " ".join(args[2:]))
    elif cmd == "reject" and len(args) >= 2:
        cmd_reject(int(args[1]), " ".join(args[2:]))
    elif cmd == "snapshot":
        cmd_snapshot()
    elif cmd == "countdown" and len(args) >= 2:
        cmd_countdown(args[1])
    elif cmd == "init":
        cmd_init()
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
