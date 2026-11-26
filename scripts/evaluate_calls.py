#!/usr/bin/env python3
"""Read-only steward evaluation summary for settled stock, volatility, and option calls.

Phase 3 of docs/specs/OPTIONS_CALLS.md and docs/research/ParadoxEdgeTrader_Evaluation_Protocol.md.
Counts, calibration, spread drag, and outcomes only—never prints private reason prose."""
import argparse
from contextlib import closing
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import sqlite3
import sys

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from core.runtime.rehearsal.calls import CALLS_FILE, NO_CALLS


def _dec(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        d = Decimal(str(value))
    except (ValueError, InvalidOperation):
        return None
    return d if d.is_finite() else None


def _hit_rate(counts):
    decided = counts["right"] + counts["wrong"]
    if decided == 0:
        return None
    return format((Decimal(counts["right"]) / Decimal(decided)).quantize(Decimal("0.0001")), "f")


def _bump(bucket, outcome):
    if outcome is None:
        bucket["open"] += 1
        return
    bucket["settled"] += 1
    if outcome in bucket:
        bucket[outcome] += 1


def _with_rate(counts):
    return {**counts, "hit_rate": _hit_rate(counts)}


def _mean(values, places="0.01"):
    if not values:
        return None
    return format((sum(values) / Decimal(len(values))).quantize(Decimal(places)), "f")


def resolve_calls_db(*, db_path=None, root=None):
    """Locate a calls.sqlite3 read-only without creating files or directories."""
    if db_path is not None:
        path = Path(db_path)
        return path if path.is_file() else None
    if root is not None:
        from core.runtime.rehearsal.store import RehearsalStore
        runs = RehearsalStore(root).list_runs(limit=50)["runs"]
        for run in runs:
            candidate = RehearsalStore(root).safe_run_file(run["run_id"], CALLS_FILE)
            if candidate.is_file():
                return candidate
    return None


def summarize_calls(db_path):
    """Return a privacy-preserving evaluation dictionary from a read-only calls.sqlite3."""
    if db_path is None or not Path(db_path).is_file():
        return {"status": "missing", "reason": "no calls database found"}

    overall = dict(NO_CALLS)
    by_kind = {k: dict(NO_CALLS) for k in ("stock", "vol", "option")}
    by_confidence = {c: dict(NO_CALLS) for c in ("low", "medium", "high")}
    by_agent = {}

    vol_implied, vol_actual = [], []
    vol_views = {"high": 0, "low": 0}
    opt_spreads, opt_returns, opt_pnls = [], [], []
    right_dir_net_loss = 0

    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=10)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

        queries = (
            ("stock", "calls", "settlements", "c.agent_id, c.confidence, NULL AS iv_view, NULL AS option_type, s.detail"),
            ("vol", "vol_calls", "vol_settlements", "c.agent_id, c.confidence, c.iv_view, NULL AS option_type, s.detail"),
            ("option", "option_calls", "option_settlements",
             "c.agent_id, c.confidence, NULL AS iv_view, c.option_type, s.detail"),
        )
        for kind, table, settle_table, cols in queries:
            if table not in tables:
                continue
            join = f"LEFT JOIN {settle_table} s USING (call_id)" if settle_table in tables else ""
            select_cols = cols if settle_table in tables else cols.replace("s.detail", "NULL AS detail")
            for row in conn.execute(f"SELECT {select_cols} FROM {table} c {join}"):
                detail = json.loads(row["detail"]) if row["detail"] is not None else None
                outcome = detail.get("outcome") if isinstance(detail, dict) else None

                _bump(overall, outcome)
                _bump(by_kind[kind], outcome)
                if row["confidence"] in by_confidence:
                    _bump(by_confidence[row["confidence"]], outcome)
                agent_bucket = by_agent.setdefault(row["agent_id"], dict(NO_CALLS))
                _bump(agent_bucket, outcome)

                if kind == "vol" and isinstance(detail, dict) and outcome in ("right", "wrong", "flat"):
                    if row["iv_view"] in vol_views:
                        vol_views[row["iv_view"]] += 1
                    imp = _dec(detail.get("implied_move_percent"))
                    act = _dec(detail.get("actual_move_percent"))
                    if imp is not None:
                        vol_implied.append(imp)
                    if act is not None:
                        vol_actual.append(act)

                if kind == "option" and isinstance(detail, dict) and outcome in ("right", "wrong", "flat"):
                    sp = _dec(detail.get("spread_percent"))
                    ret = _dec(detail.get("return_percent"))
                    pnl = _dec(detail.get("net_pnl"))
                    umove = _dec(detail.get("underlying_move_percent"))
                    if sp is not None:
                        opt_spreads.append(sp)
                    if ret is not None:
                        opt_returns.append(ret)
                    if pnl is not None:
                        opt_pnls.append(pnl)
                    if (pnl is not None and pnl < 0 and umove is not None
                            and ((row["option_type"] == "call" and umove > 0)
                                 or (row["option_type"] == "put" and umove < 0))):
                        right_dir_net_loss += 1

    return {
        "status": "ok",
        "overall": _with_rate(overall),
        "by_kind": {k: _with_rate(v) for k, v in by_kind.items()},
        "by_confidence": {k: _with_rate(v) for k, v in by_confidence.items()},
        "vol_summary": {
            "settled_with_metrics": len(vol_actual),
            "high_count": vol_views["high"],
            "low_count": vol_views["low"],
            "mean_implied_move_percent": _mean(vol_implied),
            "mean_actual_move_percent": _mean(vol_actual),
        },
        "option_summary": {
            "settled_with_metrics": len(opt_pnls),
            "mean_spread_percent": _mean(opt_spreads),
            "mean_return_percent": _mean(opt_returns),
            "total_net_pnl_per_share": format(sum(opt_pnls).normalize(), "f") if opt_pnls else None,
            "right_direction_net_loss_count": right_dir_net_loss,
        },
        "by_agent": {k: _with_rate(v) for k, v in sorted(by_agent.items())},
    }


def _format_text(summary):
    if summary.get("status") != "ok":
        return f"Calls evaluation: {summary.get('reason') or summary.get('status')}."
    ov = summary["overall"]
    lines = [
        f"Overall: {ov['open']} open, {ov['settled']} settled "
        f"(right={ov['right']}, wrong={ov['wrong']}, flat={ov['flat']}, unsettled={ov['unsettled']}, "
        f"hit_rate={ov['hit_rate'] or 'unknown'})",
        "By kind:",
    ]
    for kind, row in summary["by_kind"].items():
        lines.append(f"  {kind}: settled={row['settled']} right={row['right']} wrong={row['wrong']} "
                     f"flat={row['flat']} open={row['open']} hit_rate={row['hit_rate'] or 'unknown'}")
    lines.append("By confidence:")
    for conf, row in summary["by_confidence"].items():
        lines.append(f"  {conf}: settled={row['settled']} right={row['right']} wrong={row['wrong']} "
                     f"flat={row['flat']} hit_rate={row['hit_rate'] or 'unknown'}")
    vs = summary["vol_summary"]
    lines.append(f"Vol summary: n={vs['settled_with_metrics']} (high={vs['high_count']}, low={vs['low_count']}), "
                 f"mean_implied={vs['mean_implied_move_percent'] or 'unknown'}%, "
                 f"mean_actual={vs['mean_actual_move_percent'] or 'unknown'}%")
    os_ = summary["option_summary"]
    lines.append(f"Option summary: n={os_['settled_with_metrics']}, "
                 f"mean_spread={os_['mean_spread_percent'] or 'unknown'}%, "
                 f"mean_return={os_['mean_return_percent'] or 'unknown'}%, "
                 f"net_pnl_per_share={os_['total_net_pnl_per_share'] or 'unknown'}, "
                 f"right_direction_net_loss={os_['right_direction_net_loss_count']}")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--db", help="Path to a calls.sqlite3 file")
    group.add_argument("--root", help="Sessions root directory (uses newest run with calls.sqlite3)")
    parser.add_argument("--json", action="store_true", help="Emit JSON summary")
    args = parser.parse_args(argv)
    path = resolve_calls_db(db_path=args.db, root=args.root)
    summary = summarize_calls(path)
    print(json.dumps(summary, indent=2, sort_keys=True) if args.json else _format_text(summary))
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
