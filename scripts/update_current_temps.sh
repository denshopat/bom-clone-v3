#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATIONS_FILE="${ROOT_DIR}/data/output/current_temp_stations.txt"

python3 "${ROOT_DIR}/scripts/download_current_temps.py" --force
python3 "${ROOT_DIR}/scripts/load_daily_data.py" \
  --stations-file "${STATIONS_FILE}" \
  --data-types daily_max_temperature,daily_min_temperature \
  --force-extract
