#!/bin/bash
# Build a release tarball on a machine with git + Node (not on the VPS).
# Usage: deploy/build_release.sh [git-ref]   -> dist-release/paradoxtrader-<sha>.tar.gz
set -euo pipefail
REF="${1:-HEAD}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SHA="$(git -C "$ROOT" rev-parse --short=12 "$REF")"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
git -C "$ROOT" archive --format=tar --prefix="paradoxtrader-$SHA/" "$REF" | tar -x -C "$WORK"
( cd "$WORK/paradoxtrader-$SHA/frontend" && npm ci --silent && VITE_RUNTIME_MODE=connected npm run build && rm -rf node_modules )
echo "$SHA" > "$WORK/paradoxtrader-$SHA/RELEASE"
mkdir -p "$ROOT/dist-release"
tar -C "$WORK" -czf "$ROOT/dist-release/paradoxtrader-$SHA.tar.gz" "paradoxtrader-$SHA"
echo "$ROOT/dist-release/paradoxtrader-$SHA.tar.gz"
