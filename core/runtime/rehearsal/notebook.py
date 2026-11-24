"""The notebook: a line to remember, on every page, composted when full.

docs/specs/NOTEBOOK.md. On any move an agent may add one line (``remember`` in
its choice). The line rides inside the choice it was already making, so it
costs no request. The notebook is printed on every page of every move.

- Bounded: a line is at most LINE_CHARS; the notebook at most CAPACITY
  characters, counted as its lines joined by line breaks, so a full notebook
  is exactly one journal compost note (core.memory.compost.MAX_CONTENT_CHARS).
- Nothing fades. A line that does not fit is not written; it is recorded as
  "did not fit" and quoted back until the agent composts the notebook.
- Append-only. Lines are never edited or deleted. Composting writes every line
  into one compost note and marks those lines composted (a separate table);
  the page then starts a fresh notebook. Every line stays in the record.
- Private: one agent's lines are only ever read for that agent.
- Replay safe: one line per move, keyed by (run, wake), and composting is keyed
  by the move too, so a retried move never writes twice.

The database lives in each run (``notebook.sqlite3``) and carries to the next
day with the rest of the home.
"""
from contextlib import closing
from datetime import datetime, timezone
import sqlite3

NOTEBOOK_FILE = "notebook.sqlite3"
LINE_CHARS = 300
CAPACITY = 6000
NEARLY_FULL = 5000
SHOW_REFUSED = 3  # Lines that did not fit, quoted back (newest first).

NOTEBOOK_INSTRUCTIONS = (
    "\nNOTEBOOK: with any choice you may add \"remember\":<one line, at most 300 characters> to keep it "
    "in your notebook. It costs nothing extra, only you see it, and it is printed on every page. "
    "When it is full, compost it: {\"action\":\"compost_notebook\"} moves every "
    "line into one compost note in your journal and starts a fresh notebook. No line is owed."
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS lines (
 line_id INTEGER PRIMARY KEY,
 agent_id TEXT NOT NULL, run_id TEXT NOT NULL, wake_id TEXT NOT NULL,
 content TEXT NOT NULL, kept INTEGER NOT NULL CHECK (kept IN (0,1)), created_at TEXT NOT NULL,
 UNIQUE (run_id, wake_id)
);
CREATE TRIGGER IF NOT EXISTS lines_no_update BEFORE UPDATE ON lines
 BEGIN SELECT RAISE(ABORT, 'notebook lines are append-only'); END;
CREATE TRIGGER IF NOT EXISTS lines_no_delete BEFORE DELETE ON lines
 BEGIN SELECT RAISE(ABORT, 'notebook lines are append-only'); END;
CREATE TABLE IF NOT EXISTS composts (
 compost_id INTEGER PRIMARY KEY,
 agent_id TEXT NOT NULL, run_id TEXT NOT NULL, wake_id TEXT NOT NULL,
 journal_note_id INTEGER, last_line_id INTEGER NOT NULL, composted_at TEXT NOT NULL,
 UNIQUE (run_id, wake_id)
);
CREATE TRIGGER IF NOT EXISTS composts_no_update BEFORE UPDATE ON composts
 BEGIN SELECT RAISE(ABORT, 'notebook composts are append-only'); END;
CREATE TRIGGER IF NOT EXISTS composts_no_delete BEFORE DELETE ON composts
 BEGIN SELECT RAISE(ABORT, 'notebook composts are append-only'); END;
"""


def validate_line(value):
    """A notebook line: one line of text, 1-300 characters. Raises ValueError."""
    if (not isinstance(value, str) or not value.strip() or len(value) > LINE_CHARS
            or any(ord(c) < 32 for c in value)):
        raise ValueError("invalid notebook line")
    return value


def _used(lines):
    return len("\n".join(line["content"] for line in lines))


class NotebookStore:
    def __init__(self, path):
        self.path = path

    def _connect(self):
        connection = sqlite3.connect(str(self.path), timeout=30)
        connection.row_factory = sqlite3.Row
        connection.executescript(_SCHEMA)
        return connection

    @staticmethod
    def _since(connection, agent_id):
        row = connection.execute("SELECT MAX(last_line_id) FROM composts WHERE agent_id=?", (agent_id,)).fetchone()
        return row[0] or 0

    def _page(self, connection, agent_id):
        since = self._since(connection, agent_id)
        rows = [dict(row) for row in connection.execute(
            "SELECT line_id, wake_id, content, kept FROM lines WHERE agent_id=? AND line_id>? ORDER BY line_id",
            (agent_id, since))]
        return [r for r in rows if r["kept"]], [r for r in rows if not r["kept"]]

    def page(self, agent_id):
        """(kept lines, lines that did not fit) since the last compost, oldest first."""
        if not self.path.exists():
            return [], []
        with closing(self._connect()) as connection:
            return self._page(connection, agent_id)

    def add(self, agent_id, *, run_id, wake_id, content, now=None):
        """Write this move's line once. Returns "kept" or "did_not_fit"."""
        validate_line(content)
        stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute("SELECT kept FROM lines WHERE run_id=? AND wake_id=?",
                                          (run_id, wake_id)).fetchone()
            if existing is not None:
                return "kept" if existing["kept"] else "did_not_fit"
            kept, _ = self._page(connection, agent_id)
            fits = len("\n".join([*(line["content"] for line in kept), content])) <= CAPACITY
            connection.execute("INSERT INTO lines (agent_id, run_id, wake_id, content, kept, created_at)"
                               " VALUES (?,?,?,?,?,?)", (agent_id, run_id, wake_id, content, int(fits), stamp))
            return "kept" if fits else "did_not_fit"

    def compost(self, agent_id, *, run_id, wake_id, write_note, now=None):
        """Move every kept line into one compost note and start a fresh notebook.

        ``write_note(content)`` writes the journal compost note (idempotent for
        this move) and returns its refs. Returns those refs; [] when empty."""
        stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            done = connection.execute("SELECT journal_note_id FROM composts WHERE run_id=? AND wake_id=?",
                                      (run_id, wake_id)).fetchone()
            if done is not None:
                return [{"kind": "journal", "id": done[0]}] if done[0] is not None else []
            kept, refused = self._page(connection, agent_id)
            if not kept and not refused:
                return []
            refs = write_note("\n".join(line["content"] for line in kept)) if kept else []
            note_id = refs[0]["id"] if refs else None
            connection.execute("INSERT INTO composts (agent_id, run_id, wake_id, journal_note_id, last_line_id,"
                               " composted_at) VALUES (?,?,?,?,?,?)",
                               (agent_id, run_id, wake_id, note_id,
                                max(line["line_id"] for line in kept + refused), stamp))
            return refs

    def used(self, agent_id):
        return _used(self.page(agent_id)[0])

    def sizes(self):
        """Characters used per agent, for the Heartbeat page. Never the text."""
        if not self.path.exists():
            return {}
        with closing(self._connect()) as connection:
            agents = [row[0] for row in connection.execute("SELECT DISTINCT agent_id FROM lines")]
            return {agent: _used(self._page(connection, agent)[0]) for agent in agents}


def notebook_text(kept, refused):
    """The notebook as printed on the page. Never empty: an empty notebook says so."""
    used = _used(kept)
    head = f"YOUR NOTEBOOK ({used:,} of {CAPACITY:,} characters; only you see it)"
    lines = [head] + [f"- [{line['wake_id']}] {line['content']}" for line in kept]
    if not kept:
        lines.append("(empty: add a line with \"remember\" on any choice)")
    if refused:
        lines.append("Did not fit, so not kept (compost the notebook, then add them again if you still want them):")
        lines += [f"- [{line['wake_id']}] {line['content']}" for line in refused[-SHOW_REFUSED:][::-1]]
    if used >= CAPACITY or refused:
        lines.append("Your notebook is full. To keep writing, compost it: "
                     "{\"action\":\"compost_notebook\"}.")
    elif used >= NEARLY_FULL:
        lines.append("Your notebook is nearly full. When it is full, compost it to start a fresh one.")
    return "\n".join(lines)
