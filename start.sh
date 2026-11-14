#!/bin/bash
# LEGACY launcher for the broad api/app.py runtime.
# It is NOT the approved first-arrival or VPS recipe (see README "VPS handoff").
# The approved path is the restricted controller (scripts/rehearsal.py) and the
# read-only api/rehearsal.py inspection app behind the private gateway.
set -e

if [ "${PARADOX_ALLOW_LEGACY_APP:-}" != "1" ]; then
  echo "Refusing to start the legacy broad app (api/app.py)." >&2
  echo "Use scripts/rehearsal.py and the private gateway instead." >&2
  echo "Set PARADOX_ALLOW_LEGACY_APP=1 only for deliberate local development." >&2
  exit 1
fi

echo "=== Paradox Edge Trader v2 (legacy) — Starting ==="
echo "Legacy scheduler: ${PARADOX_LEGACY_SCHEDULER:-off} (set PARADOX_LEGACY_SCHEDULER=1 to enable)"

cd frontend
npm install --silent
npm run build
cd ..

exec uvicorn api.app:app --host 127.0.0.1 --port "${PORT:-8000}"
