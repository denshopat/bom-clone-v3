#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

python3 "$REPO_ROOT/scripts/analytics_dashboard.py"

ANALYTICS_HTML="$REPO_ROOT/data/logs/analytics/analytics.html"

if command -v xdg-open >/dev/null; then
  xdg-open "$ANALYTICS_HTML" >/dev/null 2>&1 &
elif command -v open >/dev/null; then
  open "$ANALYTICS_HTML" >/dev/null 2>&1 &
else
  echo "Open in browser: $ANALYTICS_HTML"
fi
