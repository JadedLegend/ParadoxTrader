#!/bin/bash
# Build a release tarball on a machine with git + Node (not on the VPS).
# Usage: deploy/build_release.sh [git-ref]   -> dist-release/paradoxtrader-<sha>.tar.gz
set -euo pipefail
REF="${1:-HEAD}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SHA="$(git -C "$ROOT" rev-parse --short=12 "$REF")"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
# Force LF: a Windows checkout with core.autocrlf=true would otherwise ship CRLF scripts.
git -C "$ROOT" -c core.autocrlf=false -c core.eol=lf archive --format=tar --prefix="paradoxtrader-$SHA/" "$REF" | tar -x -C "$WORK"
( cd "$WORK/paradoxtrader-$SHA/frontend" && npm ci --silent && VITE_RUNTIME_MODE=connected VITE_HOST_PROFILE=private npm run build && rm -rf node_modules )
# The broad legacy app and its launcher never ship to the host.
rm -f "$WORK/paradoxtrader-$SHA/api/app.py" "$WORK/paradoxtrader-$SHA/start.sh"
CR_FILES="$(find "$WORK/paradoxtrader-$SHA" -type f \( -name '*.sh' -o -name '*.py' -o -name '*.service' -o -name '*.timer' \) -exec sh -c 'for f; do [ "$(tr -cd "\015" < "$f" | wc -c)" -eq 0 ] || echo "$f"; done' sh {} +)"
if [ -n "$CR_FILES" ]; then
  echo "Release contains CRLF line endings; refusing to build:" >&2; echo "$CR_FILES" >&2; exit 1
fi
echo "$SHA" > "$WORK/paradoxtrader-$SHA/RELEASE"
mkdir -p "$ROOT/dist-release"
tar -C "$WORK" -czf "$ROOT/dist-release/paradoxtrader-$SHA.tar.gz" "paradoxtrader-$SHA"
echo "$ROOT/dist-release/paradoxtrader-$SHA.tar.gz"
