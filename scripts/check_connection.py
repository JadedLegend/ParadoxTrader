#!/usr/bin/env python3
"""Answer a pending Settings "Check connection" request, then exit.

Run by paradoxtrader-check.service. Sends no paid replies; see
core/runtime/openrouter_check.py.

Usage:
  check_connection.py --settings /var/lib/paradoxtrader/settings
"""
import argparse
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--settings", required=True)
    args = parser.parse_args(argv)
    from core.runtime.openrouter_check import run_pending
    result = run_pending(args.settings)
    print("no request" if result is None else f"checked: {result['status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
