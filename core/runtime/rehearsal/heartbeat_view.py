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

from .calls import NO_CALLS
from .notebook import CAPACITY as NOTEBOOK_CAPACITY, NOTEBOOK_FILE, NotebookStore
from .heartbeat import LEDGER
from .store import OWNERS

_FEEDS = (("window", "Prices", "window.json"), ("options", "Options", "options.json"),
          ("headlines", "Headlines", "headlines.json"),
          ("x", "X posts", "x_posts.json"), ("reddit", "Reddit", "reddit.json"))
_FEED_LINE_ORDER = ("headlines", "x", "reddit")  # The order feed_lines() returns its lines in.


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
    from core.market.options import options_line
    from core.market.window import window_line
    folder = Path(settings_dir) / "market"
    records = {key: _read_json(folder / name) for key, _, name in _FEEDS}
    feeds, lines = [], []
    for key, label, _ in _FEEDS:
        record = records[key] or {}
        if key == "options" and not record:
            continue  # The options view has not run yet: no row rather than an empty one.
        def format_line(value):
            if key == "window":
                return window_line(value)
            if key == "options":
                return options_line(value)
            return feed_lines({"headlines": {}, "x": {}, "reddit": {}, key: value})[_FEED_LINE_ORDER.index(key)]
        try:
            line = format_line(record)
        except (KeyError, TypeError, ValueError, AttributeError, IndexError):
            record = {"status": "unavailable", "checked_at": record.get("checked_at"),
                      "reason": "cached feed could not be read"}
            line = format_line(record)
        lines.append(line)
        state = record.get("status")
        ok = state in ("ok", "open", "closed")
        feeds.append({"feed": label, "status": "ok" if ok else ("unchecked" if not record else "unavailable"),
                      "checked_at": record.get("checked_at"),
                      "detail": ("market closed, last prices" if state == "closed" else
                                 "today's X reading limit reached" if record.get("capped") else
                                 None if ok else record.get("reason"))})
    return {"lines": lines, "feeds": feeds}


def day_view(heartbeat, *, settings_dir=None):
    """Everything the page shows, in one read."""
    status = heartbeat.status()
    today = heartbeat._local_now().date().isoformat()
    rows, run_ids = _ledger_rows(heartbeat.root, today)
    jobs, spent, counted, unknown = {}, Decimal(0), Decimal(0), False
    for run_id in run_ids:
        try:
            run = heartbeat.store.get_run(run_id)
            listed = heartbeat.store.list_jobs(run_id)
        except Exception:
            unknown = True
            continue
        counted += _money(run.get("counted_usd"))
        if run.get("unknown_cost_requests") or (run.get("known_cost_usd") is None and run.get("request_count")):
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
    try:  # Counts only: a call's reason never reaches this page.
        calls_store = heartbeat._calls_store()
        call_counts = calls_store.counts() if calls_store is not None else {}
    except Exception:
        call_counts = None
    try:  # Characters used only: a notebook's text never reaches this page.
        notebook = heartbeat._day_run_file(NOTEBOOK_FILE)
        notebook_sizes = NotebookStore(notebook).sizes() if notebook is not None else {}
    except Exception:
        notebook_sizes = None
    agents = []
    for owner in OWNERS:
        last = next((w for w in reversed(wakes) if w["agent_id"] == owner and w["outcome"] == "woke"), None)
        agents.append({"agent_id": owner, "last_wake": last,
                       "next_wake": (status.get("next_wake_by_agent") or {}).get(owner),
                       "calls": None if call_counts is None else call_counts.get(owner, dict(NO_CALLS)),
                       "notebook_chars": None if notebook_sizes is None else notebook_sizes.get(owner, 0)})
    view = dict(status)
    view["today"] = dict(status.get("today") or {}, spent_usd=format(spent, "f"), spent_complete=not unknown,
                         counted_usd=format(counted, "f"))
    view.update(choices_per_wake=heartbeat.schedule.choices_per_wake, wakes=wakes, agents=agents,
                notebook_capacity=NOTEBOOK_CAPACITY,
                window=_feeds(settings_dir) if settings_dir else {"lines": [], "feeds": []})
    return view
