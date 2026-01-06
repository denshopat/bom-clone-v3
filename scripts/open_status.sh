#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

python3 "$REPO_ROOT/scripts/update_status.py"

STATUS_HTML="$REPO_ROOT/data/logs/status.html"

if command -v xdg-open >/dev/null; then
  xdg-open "$STATUS_HTML" >/dev/null 2>&1 &
elif command -v open >/dev/null; then
  open "$STATUS_HTML" >/dev/null 2>&1 &
else
  echo "Open in browser: $STATUS_HTML"
fi
