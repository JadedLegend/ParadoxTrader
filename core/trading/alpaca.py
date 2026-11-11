"""
Alpaca Trading Integration — Paradox Edge Trader v2
=====================================================
Each agent has their own Alpaca paper trading account.
All trades go through guardrails before execution.
AUTONOMOUS_TRADING_MODE=false → trades queue for user review.
AUTONOMOUS_TRADING_MODE=true  → Paradox Hunter executes directly.

Options trading via Alpaca's options endpoints.
"""

import json
import time
from datetime import datetime, timezone
from typing import Optional

try:
    import requests
except ImportError:
    requests = None  # type: ignore

from core.runtime.config import get_alpaca_creds, get_guardrails, is_autonomous_trading

ALPACA_PAPER_BASE = "https://paper-api.alpaca.markets/v2"
ALPACA_DATA_BASE  = "https://data.alpaca.markets"


class AlpacaClient:
    """
    Thin wrapper around Alpaca REST API for one agent account.
    """

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        creds = get_alpaca_creds(agent_id)
        self.api_key    = creds["api_key"]
        self.api_secret = creds["api_secret"]
        self.base_url   = creds.get("base_url", ALPACA_PAPER_BASE)
        self._headers   = {
            "APCA-API-KEY-ID":     self.api_key,
            "APCA-API-SECRET-KEY": self.api_secret,
            "Content-Type":        "application/json",
        }

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        if requests is None:
            raise ImportError("requests required")
        resp = requests.get(
            f"{self.base_url}{path}",
            headers=self._headers,
            params=params or {},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, body: dict) -> dict:
        if requests is None:
            raise ImportError("requests required")
        resp = requests.post(
            f"{self.base_url}{path}",
            headers=self._headers,
            json=body,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def _delete(self, path: str) -> dict:
        if requests is None:
            raise ImportError("requests required")
        resp = requests.delete(
            f"{self.base_url}{path}",
            headers=self._headers,
            timeout=30,
        )
        if resp.status_code == 204:
            return {"status": "cancelled"}
        resp.raise_for_status()
        return resp.json()

    # ─── Account ─────────────────────────────────────────────────────────────

    def get_account(self) -> dict:
        return self._get("/v2/account")

    def get_portfolio_value(self) -> float:
        acct = self.get_account()
        return float(acct.get("portfolio_value", 0))

    def get_buying_power(self) -> float:
        acct = self.get_account()
        return float(acct.get("buying_power", 0))

    # ─── Positions ────────────────────────────────────────────────────────────

    def get_positions(self) -> list[dict]:
        return self._get("/v2/positions")

    def get_position(self, symbol: str) -> Optional[dict]:
        try:
            return self._get(f"/v2/positions/{symbol}")
        except Exception:
            return None

    def close_position(self, symbol: str) -> dict:
        return self._delete(f"/v2/positions/{symbol}")

    def close_all_positions(self) -> dict:
        return self._delete("/v2/positions")

    # ─── Orders ───────────────────────────────────────────────────────────────

    def get_orders(self, status: str = "open") -> list[dict]:
        return self._get("/v2/orders", params={"status": status})

    def cancel_order(self, order_id: str) -> dict:
        return self._delete(f"/v2/orders/{order_id}")

    def cancel_all_orders(self) -> dict:
        return self._delete("/v2/orders")

    def place_order(
        self,
        symbol: str,
        qty: float,
        side: str,           # "buy" | "sell"
        order_type: str = "market",
        time_in_force: str = "day",
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        extended_hours: bool = False,
        client_order_id: Optional[str] = None,
    ) -> dict:
        body = {
            "symbol": symbol,
            "qty": str(qty),
            "side": side,
            "type": order_type,
            "time_in_force": time_in_force,
        }
        if limit_price:
            body["limit_price"] = str(limit_price)
        if stop_price:
            body["stop_price"] = str(stop_price)
        if extended_hours:
            body["extended_hours"] = True
        if client_order_id:
            body["client_order_id"] = client_order_id
        return self._post("/v2/orders", body)

    # ─── Options ──────────────────────────────────────────────────────────────

    def get_options_chain(self, underlying: str, expiration_date: Optional[str] = None) -> list[dict]:
        """Fetch options chain for an underlying symbol."""
        params = {"underlying_symbols": underlying, "feed": "indicative"}
        if expiration_date:
            params["expiration_date"] = expiration_date
        try:
            data = self._get("/v2/options/contracts", params=params)
            return data.get("option_contracts", [])
        except Exception as e:
            return [{"error": str(e)}]

    def place_option_order(
        self,
        option_symbol: str,
        qty: int,
        side: str,
        order_type: str = "limit",
        limit_price: Optional[float] = None,
        time_in_force: str = "day",
    ) -> dict:
        body = {
            "symbol": option_symbol,
            "qty": str(qty),
            "side": side,
            "type": order_type,
            "time_in_force": time_in_force,
        }
        if limit_price:
            body["limit_price"] = str(limit_price)
        return self._post("/v2/orders", body)


# ─── Guardrail Layer ──────────────────────────────────────────────────────────

class GuardrailError(Exception):
    pass


def check_guardrails(
    agent_id: str,
    client: AlpacaClient,
    proposed_value: float,
) -> None:
    """
    Raises GuardrailError if the proposed trade violates any limit.
    """
    g = get_guardrails()
    acct = client.get_account()
    portfolio_value = float(acct.get("portfolio_value", 1))

    # Max position size
    max_pos_pct = float(g.get("max_position_size_pct", 10.0))
    if proposed_value > portfolio_value * (max_pos_pct / 100):
        raise GuardrailError(
            f"Position size {proposed_value:.2f} exceeds max {max_pos_pct}% of portfolio ({portfolio_value * max_pos_pct / 100:.2f})"
        )

    # Max open positions
    max_pos = int(g.get("max_open_positions", 5))
    positions = client.get_positions()
    if len(positions) >= max_pos:
        raise GuardrailError(
            f"Already at max open positions ({max_pos}). Close one before opening another."
        )

    # Daily loss check (approximate via unrealized P&L)
    daily_loss_pct = float(g.get("daily_loss_limit_pct", 5.0))
    unrealized_pl = float(acct.get("unrealized_pl", 0))
    if unrealized_pl < 0:
        loss_pct = abs(unrealized_pl) / portfolio_value * 100
        if loss_pct >= daily_loss_pct:
            raise GuardrailError(
                f"Daily loss limit reached: {loss_pct:.1f}% >= {daily_loss_pct}%"
            )


# ─── Trade Queue (for non-autonomous mode) ────────────────────────────────────

import sqlite3
from pathlib import Path

QUEUE_DB = Path(__file__).parent.parent.parent / "data" / "trade_queue.sqlite3"

QUEUE_SCHEMA = """
CREATE TABLE IF NOT EXISTS trade_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    proposal TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    reviewer_notes TEXT,
    created_at TEXT NOT NULL,
    reviewed_at TEXT
);
"""


class TradeQueue:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = str(db_path or QUEUE_DB)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(QUEUE_SCHEMA)
            conn.commit()

    def enqueue(self, agent_id: str, proposal: dict) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "INSERT INTO trade_queue (agent_id, proposal, created_at) VALUES (?, ?, ?)",
                (agent_id, json.dumps(proposal), now)
            )
            conn.commit()
            return cur.lastrowid

    def get_pending(self) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, agent_id, proposal, status, created_at FROM trade_queue WHERE status='pending' ORDER BY created_at ASC"
            ).fetchall()
        return [{"id": r[0], "agent_id": r[1], "proposal": json.loads(r[2]), "status": r[3], "created_at": r[4]} for r in rows]

    def approve(self, trade_id: int, notes: str = "") -> bool:
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE trade_queue SET status='approved', reviewer_notes=?, reviewed_at=? WHERE id=?",
                (notes, now, trade_id)
            )
            conn.commit()
        return True

    def reject(self, trade_id: int, notes: str = "") -> bool:
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE trade_queue SET status='rejected', reviewer_notes=?, reviewed_at=? WHERE id=?",
                (notes, now, trade_id)
            )
            conn.commit()
        return True


def submit_trade(agent_id: str, proposal: dict) -> dict:
    """
    Either execute immediately (autonomous mode) or queue for review.
    """
    if is_autonomous_trading():
        # Execute directly via Alpaca
        client = AlpacaClient(agent_id)
        estimated_value = float(proposal.get("estimated_value", 0))
        try:
            check_guardrails(agent_id, client, estimated_value)
        except GuardrailError as e:
            return {"status": "blocked", "reason": str(e)}

        # Place the order
        try:
            order = client.place_option_order(
                option_symbol=proposal["symbol"],
                qty=proposal.get("qty", 1),
                side=proposal.get("side", "buy"),
                order_type=proposal.get("order_type", "limit"),
                limit_price=proposal.get("limit_price"),
            )
            return {"status": "executed", "order": order}
        except Exception as e:
            return {"status": "error", "reason": str(e)}
    else:
        # Queue for user review
        queue = TradeQueue()
        qid = queue.enqueue(agent_id, proposal)
        return {"status": "queued", "queue_id": qid, "message": "Trade queued for your review."}
