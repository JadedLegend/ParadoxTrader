"""The heartbeat page's data: read-only, plain, never a key or a private note.

See docs/specs/HEARTBEAT_PAGE.md. Built on ``Heartbeat.status()`` so the page
and the heartbeat always agree on why something is or is not happening, plus
today's wake ledger, the day runs' totals and the market caches.
"""
from contextlib import closing
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import sqlite3

from .heartbeat import LEDGER
from .store import OWNERS

_FEEDS = (("window", "Prices", "window.json"), ("headlines", "Headlines", "headlines.json"),
          ("x", "X posts", "x_posts.json"), ("reddit", "Reddit", "reddit.json"))


def _money(value):
    try:
        return Decimal(str(value)) if value is not None else Decimal(0)
    except (InvalidOperation, ValueError):
        return Decimal(0)


def _read_json(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _ledger_rows(root, today):
    path = Path(root) / LEDGER
    if not path.exists():
        return [], []
    with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=10)) as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(row) for row in conn.execute(
            "SELECT agent_id,scheduled_at,outcome,run_id,wake_id,wake_status,note FROM wake_slots "
            "WHERE local_date=? AND outcome != 'clock_only' ORDER BY scheduled_at", (today,))]
        runs = [row[0] for row in conn.execute(
            "SELECT run_id FROM days WHERE local_date=? ORDER BY opened_at", (today,))]
    return rows, runs


def _choices(row, job):
    note = row.get("note") or ""
    if note.startswith("choices: "):
        return [part.strip() for part in note[len("choices: "):].split(",") if part.strip()]
    if job and job.get("action"):
        return [job["action"]]
    return []


def _feeds(settings_dir):
    from core.market.feeds import feed_lines
    from core.market.window import window_line
    folder = Path(settings_dir) / "market"
    records = {key: _read_json(folder / name) for key, _, name in _FEEDS}
    feeds = []
    for key, label, _ in _FEEDS:
        record = records[key] or {}
        state = record.get("status")
        ok = state in ("ok", "open", "closed")
        feeds.append({"feed": label, "status": "ok" if ok else ("unchecked" if not record else "unavailable"),
                      "checked_at": record.get("checked_at"),
                      "detail": ("market closed, last prices" if state == "closed" else
                                 "today's X reading limit reached" if record.get("capped") else
                                 None if ok else record.get("reason"))})
    lines = [window_line(records["window"])]
    lines += feed_lines({"headlines": records["headlines"] or {}, "x": records["x"] or {},
                         "reddit": records["reddit"] or {}})
    return {"lines": lines, "feeds": feeds}


def day_view(heartbeat, *, settings_dir=None):
    """Everything the page shows, in one read."""
    status = heartbeat.status()
    today = heartbeat._local_now().date().isoformat()
    rows, run_ids = _ledger_rows(heartbeat.root, today)
    jobs, spent, reserved, unknown = {}, Decimal(0), Decimal(0), False
    for run_id in run_ids:
        try:
            run = heartbeat.store.get_run(run_id)
            listed = heartbeat.store.list_jobs(run_id)
        except Exception:
            unknown = True
            continue
        reserved += _money(run.get("reserved_usd"))
        if run.get("known_cost_usd") is None and run.get("request_count"):
            unknown = True
        spent += _money(run.get("known_cost_usd"))
        for job in listed:
            jobs[(run_id, job["wake_id"])] = job
    wakes = []
    for row in rows:
        job = jobs.get((row["run_id"], row["wake_id"])) if row["wake_id"] else None
        note = row.get("note") or ""
        wakes.append({"agent_id": row["agent_id"], "scheduled_at": row["scheduled_at"],
                      "outcome": row["outcome"], "wake_status": row["wake_status"],
                      "choices": _choices(row, job), "model": (job or {}).get("requested_model"),
                      "note": None if not note or note.startswith("choices: ") else note})
    agents = []
    for owner in OWNERS:
        last = next((w for w in reversed(wakes) if w["agent_id"] == owner and w["outcome"] == "woke"), None)
        agents.append({"agent_id": owner, "last_wake": last,
                       "next_wake": (status.get("next_wake_by_agent") or {}).get(owner)})
    view = dict(status)
    view["today"] = dict(status.get("today") or {}, spent_usd=format(spent, "f"), spent_complete=not unknown,
                         reserved_usd=format(reserved, "f"))
    view.update(choices_per_wake=heartbeat.schedule.choices_per_wake, wakes=wakes, agents=agents,
                window=_feeds(settings_dir) if settings_dir else {"lines": [], "feeds": []})
    return view
