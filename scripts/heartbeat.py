#!/usr/bin/env python3
"""The heartbeat's command line: tick, status, pause, resume, stop.

``tick`` is what the systemd timer runs every minute. It starts the agents'
wakes that are due, each on its own staggered clock, at most a few per tick;
see core/runtime/rehearsal/heartbeat.py for every limit it enforces. With
``"dispatch": "clock-only"`` it only records the wake times.

Real-model wakes additionally need ``mode: real``, a ``models_file`` in
the config, and REHEARSAL_OPENROUTER_API_KEY in the environment. Without the
key a real tick refuses before preparing anything. Nothing here can trade.

Usage:
  heartbeat.py --root /var/lib/paradoxtrader/sessions --config /etc/paradoxtrader/heartbeat.json tick
"""
import argparse
from contextlib import ExitStack
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _rehearsal_cli():
    spec = importlib.util.spec_from_file_location("rehearsal_cli", REPO / "scripts" / "rehearsal.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def day_input_bytes(manifest):
    """The larger day page (DAY_MAX_INPUT_BYTES), but no more than every chosen
    model's context leaves after the full day reply room, so a bigger page
    never squeezes a thinking model's answer. Never below the rehearsal page,
    so a small model keeps today's behaviour."""
    from core.runtime.rehearsal.provider import DAY_MAX_INPUT_BYTES, DAY_MAX_OUTPUT_TOKENS
    rows = manifest["catalog_snapshot"]["models"]
    room = min([DAY_MAX_INPUT_BYTES]
               + [row["context_length"] - min(DAY_MAX_OUTPUT_TOKENS, row["max_completion_tokens"])
                  for row in rows])
    return max(manifest["limits"]["max_input_bytes"], room)


def day_output_tokens(manifest):
    """Room for models that think first: up to DAY_MAX_OUTPUT_TOKENS, but no
    more than every chosen model can give, so one small model never stops the
    day from opening. Never below the limit the day already had."""
    from core.runtime.rehearsal.provider import DAY_MAX_OUTPUT_TOKENS
    rows = manifest["catalog_snapshot"]["models"]
    room = min([DAY_MAX_OUTPUT_TOKENS]
               + [row["max_completion_tokens"] for row in rows]
               + [row["context_length"] - manifest["limits"]["max_input_bytes"] for row in rows])
    return max(manifest["limits"]["max_output_tokens"], room)


def build(root, config_path):
    from core.runtime.rehearsal.heartbeat import Heartbeat, load_schedule
    from core.runtime.rehearsal.store import RehearsalStore
    cli = _rehearsal_cli()
    schedule = load_schedule(config_path)
    store = RehearsalStore(cli.root_path(root))

    settings = None
    if schedule.settings_dir:
        from core.runtime.owner_settings import OwnerSettings
        settings = OwnerSettings(schedule.settings_dir)

    def key():
        chosen = settings.key() if settings is not None else None
        return chosen or os.environ.get("REHEARSAL_OPENROUTER_API_KEY", "").strip() or None

    def prepare_day(budget_usd, wakes_per_agent, models=None):
        if schedule.mode == "real":
            manifest = cli.manifest_for("real", models_file=schedule.models_file, models=models,
                                        fetch_catalog=True, budget_usd=budget_usd)
        else:
            manifest = cli.manifest_for("offline", models=models, budget_usd=budget_usd)
        manifest["kind"] = "day"
        manifest["limits"]["wakes_per_agent"] = wakes_per_agent
        manifest["limits"]["max_requests"] = 2 * wakes_per_agent * 7
        manifest["limits"]["max_input_bytes"] = day_input_bytes(manifest)
        manifest["limits"]["max_output_tokens"] = day_output_tokens(manifest)
        return store.prepare(manifest)["run_id"]

    def market_window(owner):
        """The shared read-only price window, read with the designated data
        account's paper key (see OwnerSettings.data_credentials). None without Settings."""
        if settings is None:
            return None
        from core.market.window import DEFAULT_WATCHLIST, MarketWindow
        symbols = settings.watchlist() or list(DEFAULT_WATCHLIST)
        return MarketWindow(Path(schedule.settings_dir) / "market", symbols, settings.data_credentials).read

    def options_view():
        """The shared read-only options view for one ticker. None without Settings."""
        if settings is None:
            return None
        from core.market.options import OptionsView
        from core.market.window import DEFAULT_WATCHLIST, MarketWindow
        symbol = settings.options_symbol() or "SPY"
        window = MarketWindow(Path(schedule.settings_dir) / "market",
                              settings.watchlist() or list(DEFAULT_WATCHLIST), settings.data_credentials)

        def price():
            record = window.cached() or {}
            return next((q.get("last") for q in record.get("quotes") or [] if q.get("symbol") == symbol), None)

        return OptionsView(Path(schedule.settings_dir) / "market", symbol, settings.data_credentials, price).read

    def market_feeds():
        """Shared cached headlines and X posts (read-only). None without Settings."""
        if settings is None:
            return None
        from core.market.feeds import DEFAULT_SUBREDDITS, MarketFeeds
        from core.market.window import DEFAULT_WATCHLIST
        symbols = settings.watchlist() or list(DEFAULT_WATCHLIST)
        return MarketFeeds(Path(schedule.settings_dir) / "market", symbols, settings.secret,
                           subreddits=settings.subreddits() or list(DEFAULT_SUBREDDITS)).read

    def run_wake(run_id, owner, step=None):
        from core.runtime.rehearsal.controller import RehearsalController, snapshot_profiles
        from core.runtime.rehearsal.provider import OpenRouterTransport
        snapshot_profiles(store, run_id, REPO)
        if schedule.mode == "real":
            transport = OpenRouterTransport(key())
            return RehearsalController(store, run_id, transport=transport, repo_root=REPO,
                                       market=market_window(owner), options=options_view(),
                                       feeds=market_feeds()).run_wake(owner, step=step)
        from core.runtime.rehearsal.examples import ScriptedHTTP
        transport = OpenRouterTransport("offline-scripted-not-a-credential", http_post=ScriptedHTTP())
        with ExitStack() as blocked:
            for target, method in [(socket, "create_connection"), (socket.socket, "connect"), (socket.socket, "connect_ex")]:
                blocked.enter_context(mock.patch.object(target, method, side_effect=AssertionError("Offline wakes forbid networking")))
            return RehearsalController(store, run_id, transport=transport, repo_root=REPO).run_wake(owner, step=step)

    return Heartbeat(store, schedule, prepare_day=prepare_day, run_wake=run_wake,
                     settings=settings, key_present=lambda: key() is not None)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("command", choices=["tick", "status", "pause", "resume", "stop"])
    args = parser.parse_args(argv)
    heartbeat = build(args.root, args.config)
    if (args.command == "tick" and heartbeat.schedule.mode == "real" and heartbeat.schedule.dispatch == "live"
            and not heartbeat.key_present()):
        # Only starting real gatherings needs the key, and the check comes
        # before any decision is recorded. status/pause/resume/stop never do.
        raise ValueError("dedicated_rehearsal_key_missing")
    result = getattr(heartbeat, args.command)()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        # Bounded codes only: never keys, provider bodies or raw exceptions.
        code = str(exc) if str(exc) in {"dedicated_rehearsal_key_missing", "heartbeat_already_running",
                                        "invalid_heartbeat_config"} else "heartbeat_operation_failed"
        report = {"error": code, "type": type(exc).__name__}
        from core.runtime.rehearsal.provider import ManifestError
        if isinstance(exc, ManifestError):
            report["detail"] = str(exc)  # Manifest codes are fixed strings, such as invalid_catalog_price.
        print(json.dumps(report), file=sys.stderr)
        raise SystemExit(1)
