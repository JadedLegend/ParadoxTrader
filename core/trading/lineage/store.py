"""Durable optional inquiries and mock-confirmed execution projections.

Every operation opens its own connection. BEGIN IMMEDIATE serializes write-side
idempotency and close reservations, including across restarted store objects.
No provider, runtime, memory, configuration, or network imports belong here.
"""
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from core.trading.queue import QUEUE_DB, ensure_private_db_file
from .errors import LineageAccessError, LineageConflict, LineageError, LineageNotFound
from .schema import ensure_lineage_schema
from .validation import canonical_json, integer, text, validate_structure

_NAMESPACE = uuid.UUID("7c9e34b4-ecec-42db-ae99-816313fa18b5")
_TERMINAL = frozenset({"filled", "canceled", "rejected"})


def _now():
    return datetime.now(timezone.utc).isoformat()


def _id():
    return str(uuid.uuid4())


def _stable_id(kind, *parts):
    return str(uuid.uuid5(_NAMESPACE, canonical_json([kind, *parts])))


def _event(conn, inquiry_id, agent_id, kind, payload, now=None):
    event_id = _id()
    conn.execute("INSERT INTO lineage_events (event_id,inquiry_id,agent_id,kind,payload,created_at) "
                 "VALUES (?,?,?,?,?,?)", (event_id, inquiry_id, agent_id, kind, canonical_json(payload), now or _now()))
    return event_id


def append_proposal_review(conn, queue_row, status, notes, now):
    """Queue-owned transaction hook; return False on corrupt/conflicting linkage."""
    proposal = conn.execute("SELECT proposal_id,inquiry_id,agent_id,queue_id FROM lineage_proposals "
                            "WHERE proposal_id=? LIMIT 1", (queue_row["lineage_proposal_id"],)).fetchone()
    if (proposal is None or proposal["agent_id"] != queue_row["agent_id"]
            or proposal["queue_id"] != queue_row["id"]):
        return False
    inquiry = conn.execute("SELECT agent_id FROM lineage_inquiries WHERE inquiry_id=? LIMIT 1",
                           (proposal["inquiry_id"],)).fetchone()
    if inquiry is None or inquiry["agent_id"] != proposal["agent_id"]:
        return False
    if conn.execute("SELECT order_id FROM lineage_orders WHERE proposal_id=? LIMIT 1",
                    (proposal["proposal_id"],)).fetchone():
        return False
    _event(conn, proposal["inquiry_id"], proposal["agent_id"], "proposal_reviewed",
           {"proposal_id": proposal["proposal_id"], "queue_id": queue_row["id"],
            "review_status": status, "reviewer_notes": notes, "source": "operator"}, now)
    conn.execute("UPDATE lineage_inquiries SET updated_at=? WHERE inquiry_id=?", (now, proposal["inquiry_id"]))
    return True


class LineageStore:
    def __init__(self, db_path=None):
        # Deliberately lazy: factories/imports do not create a file or query records.
        self.db_path = str(QUEUE_DB if db_path is None else db_path)

    @contextmanager
    def _connection(self):
        ensure_private_db_file(self.db_path)
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            conn.execute("BEGIN IMMEDIATE")
            ensure_lineage_schema(conn)
            yield conn
            conn.commit()
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            raise LineageConflict(str(exc)) from exc
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _agent(agent_id):
        return text(agent_id, "agent_id", maximum=100, empty=False)

    @staticmethod
    def _owner(conn, table, key, record_id, agent_id):
        text(record_id, key, maximum=100, empty=False)
        row = conn.execute(f"SELECT * FROM {table} WHERE {key}=? LIMIT 1", (record_id,)).fetchone()
        if row is None:
            raise LineageNotFound(f"{key} not found")
        if row["agent_id"] != agent_id:
            raise LineageAccessError("record belongs to a different agent")
        return row

    def _inquiry(self, conn, inquiry_id, agent_id):
        self._agent(agent_id)
        return self._owner(conn, "lineage_inquiries", "inquiry_id", inquiry_id, agent_id)

    @staticmethod
    def _operation(conn, agent_id, operation_key, kind, payload):
        text(operation_key, "operation_key", maximum=200, empty=False)
        encoded = canonical_json(payload)
        previous = conn.execute("SELECT kind,payload,result_id FROM lineage_operations "
                                "WHERE agent_id=? AND operation_key=? LIMIT 1", (agent_id, operation_key)).fetchone()
        if previous:
            if previous["kind"] != kind or previous["payload"] != encoded:
                raise LineageConflict("operation_key already used with a different payload")
            return previous["result_id"]
        return None

    @staticmethod
    def _record_operation(conn, agent_id, operation_key, kind, payload, result_id, now):
        conn.execute("INSERT INTO lineage_operations "
                     "(agent_id,operation_key,kind,payload,result_id,created_at) VALUES (?,?,?,?,?,?)",
                     (agent_id, operation_key, kind, canonical_json(payload), result_id, now))

    @staticmethod
    def _touch(conn, inquiry_id, now):
        conn.execute("UPDATE lineage_inquiries SET updated_at=? WHERE inquiry_id=?", (now, inquiry_id))

    def create_inquiry(self, agent_id, title, *, phase=0, visibility="owner", operation_key):
        self._agent(agent_id)
        text(title, "title", maximum=500, empty=False)
        integer(phase, "phase", minimum=0, maximum=100)
        if visibility not in ("owner", "community"):
            raise LineageError("visibility must be owner or community")
        payload = {"title": title, "phase": phase, "visibility": visibility}
        with self._connection() as conn:
            previous = self._operation(conn, agent_id, operation_key, "create_inquiry", payload)
            if previous:
                return previous
            inquiry_id, now = _id(), _now()
            conn.execute("INSERT INTO lineage_inquiries "
                         "(inquiry_id,agent_id,title,state,phase,visibility,created_at,updated_at) "
                         "VALUES (?,?,?,'open',?,?,?,?)", (inquiry_id, agent_id, title, phase, visibility, now, now))
            _event(conn, inquiry_id, agent_id, "inquiry_created", payload, now)
            self._record_operation(conn, agent_id, operation_key, "create_inquiry", payload, inquiry_id, now)
            return inquiry_id

    def add_entry(self, inquiry_id, agent_id, kind, content, *, source="agent", operation_key):
        self._agent(agent_id)
        if kind not in ("observation", "interpretation"):
            raise LineageError("entry kind must be observation or interpretation")
        if source not in ("agent", "operator", "external"):
            raise LineageError("entry source must be agent, operator, or external")
        text(content, "content", empty=False)
        payload = {"inquiry_id": inquiry_id, "kind": kind, "content": content, "source": source}
        with self._connection() as conn:
            self._inquiry(conn, inquiry_id, agent_id)
            previous = self._operation(conn, agent_id, operation_key, "add_entry", payload)
            if previous:
                return previous
            entry_id, now = _id(), _now()
            conn.execute("INSERT INTO lineage_entries (entry_id,inquiry_id,agent_id,kind,content,source,created_at) "
                         "VALUES (?,?,?,?,?,?,?)", (entry_id, inquiry_id, agent_id, kind, content, source, now))
            _event(conn, inquiry_id, agent_id, "entry_added", {"entry_id": entry_id, "kind": kind, "source": source}, now)
            self._touch(conn, inquiry_id, now)
            self._record_operation(conn, agent_id, operation_key, "add_entry", payload, entry_id, now)
            return entry_id

    def set_inquiry_state(self, inquiry_id, agent_id, state, *, reason="", operation_key):
        self._agent(agent_id)
        if state not in ("open", "paused", "abandoned"):
            raise LineageError("inquiry state must be open, paused, or abandoned")
        text(reason, "reason")
        payload = {"inquiry_id": inquiry_id, "state": state, "reason": reason}
        with self._connection() as conn:
            inquiry = self._inquiry(conn, inquiry_id, agent_id)
            previous = self._operation(conn, agent_id, operation_key, "set_inquiry_state", payload)
            if previous:
                return previous
            now = _now()
            kind = "inquiry_revisited" if state == "open" and inquiry["state"] != "open" else "inquiry_state_changed"
            event_id = _event(conn, inquiry_id, agent_id, kind,
                              {"from_state": inquiry["state"], "state": state, "reason": reason}, now)
            conn.execute("UPDATE lineage_inquiries SET state=?,updated_at=? WHERE inquiry_id=?", (state, now, inquiry_id))
            self._record_operation(conn, agent_id, operation_key, "set_inquiry_state", payload, event_id, now)
            return event_id

    def create_proposal(self, inquiry_id, agent_id, structure, *, thesis="", horizon="", uncertainty="", operation_key):
        self._agent(agent_id)
        structure = validate_structure(structure)
        for name, value in (("thesis", thesis), ("horizon", horizon), ("uncertainty", uncertainty)):
            text(value, name)
        payload = {"inquiry_id": inquiry_id, "structure": structure, "thesis": thesis,
                   "horizon": horizon, "uncertainty": uncertainty}
        with self._connection() as conn:
            self._inquiry(conn, inquiry_id, agent_id)
            previous = self._operation(conn, agent_id, operation_key, "create_proposal", payload)
            if previous:
                return previous
            proposal_id, now = _id(), _now()
            queue_payload = {key: structure[key] for key in ("symbol", "qty", "side", "order_type", "limit_price")}
            queue_payload.update({"inquiry_id": inquiry_id, "lineage_proposal_id": proposal_id, "mode": "mock"})
            queue_id = conn.execute("INSERT INTO trade_queue "
                                    "(agent_id,proposal,status,created_at,lineage_proposal_id) VALUES (?,?,'pending',?,?)",
                                    (agent_id, canonical_json(queue_payload), now, proposal_id)).lastrowid
            conn.execute("INSERT INTO lineage_proposals "
                         "(proposal_id,inquiry_id,agent_id,queue_id,structure,thesis,horizon,uncertainty,created_at) "
                         "VALUES (?,?,?,?,?,?,?,?,?)",
                         (proposal_id, inquiry_id, agent_id, queue_id, canonical_json(structure), thesis, horizon, uncertainty, now))
            _event(conn, inquiry_id, agent_id, "proposal_created", {"proposal_id": proposal_id, "queue_id": queue_id}, now)
            self._touch(conn, inquiry_id, now)
            self._record_operation(conn, agent_id, operation_key, "create_proposal", payload, proposal_id, now)
            return proposal_id

    def add_review(self, inquiry_id, agent_id, content, *, proposal_id=None, order_id=None, position_id=None, operation_key):
        self._agent(agent_id)
        text(content, "content", empty=False)
        payload = {"inquiry_id": inquiry_id, "content": content, "proposal_id": proposal_id,
                   "order_id": order_id, "position_id": position_id}
        with self._connection() as conn:
            self._inquiry(conn, inquiry_id, agent_id)
            proposal = order = None
            if proposal_id is not None:
                proposal = self._owner(conn, "lineage_proposals", "proposal_id", proposal_id, agent_id)
                if proposal["inquiry_id"] != inquiry_id:
                    raise LineageConflict("review proposal is not related to inquiry")
            if order_id is not None:
                order = self._owner(conn, "lineage_orders", "order_id", order_id, agent_id)
                if order["inquiry_id"] != inquiry_id or (proposal and order["proposal_id"] != proposal_id):
                    raise LineageConflict("review order is not related to inquiry/proposal")
            if position_id is not None:
                self._owner(conn, "lineage_positions", "position_id", position_id, agent_id)
                query = "SELECT fill_id FROM lineage_fills WHERE inquiry_id=? AND agent_id=? AND position_id=?"
                params = [inquiry_id, agent_id, position_id]
                if proposal_id is not None:
                    query += " AND proposal_id=?"
                    params.append(proposal_id)
                if order_id is not None:
                    query += " AND order_id=?"
                    params.append(order_id)
                if not conn.execute(query + " LIMIT 1", params).fetchone():
                    raise LineageConflict("review position is not fill-related to inquiry/proposal/order")
            previous = self._operation(conn, agent_id, operation_key, "add_review", payload)
            if previous:
                return previous
            review_id, now = _id(), _now()
            conn.execute("INSERT INTO lineage_reviews "
                         "(review_id,inquiry_id,agent_id,content,proposal_id,order_id,position_id,created_at) VALUES (?,?,?,?,?,?,?,?)",
                         (review_id, inquiry_id, agent_id, content, proposal_id, order_id, position_id, now))
            _event(conn, inquiry_id, agent_id, "review_added",
                   {"review_id": review_id, "proposal_id": proposal_id, "order_id": order_id, "position_id": position_id}, now)
            self._touch(conn, inquiry_id, now)
            self._record_operation(conn, agent_id, operation_key, "add_review", payload, review_id, now)
            return review_id

    def _proposal(self, conn, proposal_id, agent_id):
        self._agent(agent_id)
        proposal = self._owner(conn, "lineage_proposals", "proposal_id", proposal_id, agent_id)
        self._inquiry(conn, proposal["inquiry_id"], agent_id)
        queue = conn.execute("SELECT agent_id,lineage_proposal_id,status FROM trade_queue WHERE id=? LIMIT 1",
                             (proposal["queue_id"],)).fetchone()
        if queue is None or queue["agent_id"] != agent_id or queue["lineage_proposal_id"] != proposal_id:
            raise LineageConflict("proposal queue linkage does not match")
        result = dict(proposal)
        result["structure"] = json.loads(result["structure"])
        result["review_status"] = queue["status"]
        return result

    def get_proposal(self, proposal_id, agent_id):
        with self._connection() as conn:
            return self._proposal(conn, proposal_id, agent_id)

    @staticmethod
    def _order_dto(row):
        result = dict(row)
        result.pop("snapshot", None)
        result["structure"] = json.loads(result["structure"])
        return result

    def _order(self, conn, order_id, agent_id):
        self._agent(agent_id)
        row = self._owner(conn, "lineage_orders", "order_id", order_id, agent_id)
        proposal = self._proposal(conn, row["proposal_id"], agent_id)
        if row["inquiry_id"] != proposal["inquiry_id"] or row["queue_id"] != proposal["queue_id"]:
            raise LineageConflict("order references do not match proposal")
        if json.loads(row["structure"]) != proposal["structure"] or row["qty"] != proposal["structure"]["qty"]:
            raise LineageConflict("order structure does not match proposal")
        return row

    def prepare_order(self, proposal_id, agent_id):
        with self._connection() as conn:
            proposal = self._proposal(conn, proposal_id, agent_id)
            if proposal["review_status"] != "approved":
                raise LineageConflict("existing queue approval is required")
            existing = conn.execute("SELECT order_id FROM lineage_orders WHERE proposal_id=? LIMIT 1", (proposal_id,)).fetchone()
            if existing:
                return self._order_dto(self._order(conn, existing["order_id"], agent_id))
            structure = validate_structure(proposal["structure"])
            if structure["intent"] == "close":
                position = conn.execute("SELECT qty FROM lineage_positions WHERE agent_id=? AND symbol=? LIMIT 1",
                                        (agent_id, structure["symbol"])).fetchone()
                holdings = 0 if position is None else position["qty"]
                reserved = 0
                # Only confirmed terminal states release reservations. Unknown/unavailable
                # close submissions retain the remaining quantity, never presumed absent.
                for row in conn.execute("SELECT status,sync_state,qty,filled_qty,structure FROM lineage_orders WHERE agent_id=?", (agent_id,)):
                    other = json.loads(row["structure"])
                    if other["symbol"] == structure["symbol"] and other["intent"] == "close":
                        if row["status"] not in _TERMINAL:
                            reserved += row["qty"] - row["filled_qty"]
                if structure["qty"] > holdings - reserved:
                    raise LineageConflict("insufficient confirmed unreserved long contracts")
            order_id, now = _stable_id("order", proposal_id), _now()
            client_order_id = "lineage-" + _stable_id("client_order", proposal_id)
            conn.execute("INSERT INTO lineage_orders "
                         "(order_id,proposal_id,inquiry_id,agent_id,queue_id,client_order_id,status,sync_state,qty,structure,created_at,updated_at) "
                         "VALUES (?,?,?,?,?,?,'pending_submission','pending',?,?,?,?)",
                         (order_id, proposal_id, proposal["inquiry_id"], agent_id, proposal["queue_id"], client_order_id,
                          structure["qty"], canonical_json(structure), now, now))
            _event(conn, proposal["inquiry_id"], agent_id, "order_prepared",
                   {"proposal_id": proposal_id, "order_id": order_id, "client_order_id": client_order_id, "broker": "mock"}, now)
            self._touch(conn, proposal["inquiry_id"], now)
            return self._order_dto(self._order(conn, order_id, agent_id))

    def get_order(self, order_id, agent_id):
        with self._connection() as conn:
            return self._order_dto(self._order(conn, order_id, agent_id))

    def mark_order_issue(self, order_id, agent_id, category):
        if category not in ("submission_unknown", "unavailable", "failed"):
            raise LineageError("unknown order issue category")
        with self._connection() as conn:
            order = self._order(conn, order_id, agent_id)
            status = order["status"]
            if category == "submission_unknown" and order["broker_revision"] == 0:
                status = "submission_unknown"
            if order["sync_state"] == category and status == order["status"]:
                return self._order_dto(order)
            now = _now()
            conn.execute("UPDATE lineage_orders SET status=?,sync_state=?,updated_at=? WHERE order_id=?",
                         (status, category, now, order_id))
            _event(conn, order["inquiry_id"], agent_id, "order_issue", {"order_id": order_id, "category": category}, now)
            self._touch(conn, order["inquiry_id"], now)
            return self._order_dto(self._order(conn, order_id, agent_id))

    def apply_snapshot(self, order_id, agent_id, snapshot):
        from .projections import apply_snapshot
        return apply_snapshot(self, order_id, agent_id, snapshot)

    def list_inquiries(self, agent_id, *, viewer_agent_id=None, phase=0, operator=False, limit=50, offset=0):
        from .reads import list_inquiries
        return list_inquiries(self, agent_id, viewer_agent_id=viewer_agent_id, phase=phase,
                              operator=operator, limit=limit, offset=offset)

    def get_inquiry(self, inquiry_id, *, viewer_agent_id=None, phase=0, operator=False):
        from .reads import get_inquiry
        return get_inquiry(self, inquiry_id, viewer_agent_id=viewer_agent_id, phase=phase, operator=operator)


def get_default_lineage_store():
    """Explicit factory only; construction neither initializes nor reads the DB."""
    return LineageStore(QUEUE_DB)


get_default_store = get_default_lineage_store
