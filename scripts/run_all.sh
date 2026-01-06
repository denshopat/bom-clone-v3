#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_FILE="$REPO_ROOT/data/logs/run_state.env"

mkdir -p "$REPO_ROOT/data/logs"
cd "$REPO_ROOT"

# Steps:
# 1 update_lists
# 2 download_metadata
# 3 refresh_metadata
# 4 build_station_table
# 5 setup_database
# 6 extract_equipment
# 7 setup_equipment
# 8 download_zips
# 9 load_daily_data

load_state() {
  if [[ -f "$STATE_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$STATE_FILE"
  fi
}

save_state() {
  cat <<STATE > "$STATE_FILE"
LAST_STEP="$1"
STATE
}

should_run_step() {
  local step="$1"
  local force_step="$2"
  local from_step="$3"
  local to_step="$4"

  if [[ -n "$force_step" && "$step" == "$force_step" ]]; then
    return 0
  fi

  if [[ -n "$from_step" && "$step" -lt "$from_step" ]]; then
    return 1
  fi

  if [[ -n "$to_step" && "$step" -gt "$to_step" ]]; then
    return 1
  fi

  if [[ -n "${LAST_STEP:-}" && -z "$from_step" ]]; then
    if [[ "$step" -le "$LAST_STEP" ]]; then
      return 1
    fi
  fi

  return 0
}

run_step() {
  local step_num="$1"
  local step_name="$2"
  shift 2

  if should_run_step "$step_num" "$FORCE_STEP" "$FROM_STEP" "$TO_STEP"; then
    echo "==> Step $step_num: $step_name"
    "$@"
    save_state "$step_num"
  else
    echo "==> Step $step_num: $step_name (skipped)"
  fi
}

FROM_STEP=""
TO_STEP=""
FORCE_STEP=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --status)
      if [[ -f "$STATE_FILE" ]]; then
        # shellcheck disable=SC1090
        source "$STATE_FILE"
        echo "State file: $STATE_FILE"
        echo "Last step: ${LAST_STEP:-none}"
      else
        echo "State file: $STATE_FILE"
        echo "Last step: none"
      fi
      exit 0
      ;;
    --from)
      FROM_STEP="$2"
      shift 2
      ;;
    --to)
      TO_STEP="$2"
      shift 2
      ;;
    --force)
      FORCE_STEP="$2"
      shift 2
      ;;
    --reset)
      rm -f "$STATE_FILE"
      shift 1
      ;;
    *)
      echo "Unknown arg: $1"
      exit 1
      ;;
  esac
done

load_state

echo "State file: $STATE_FILE"
echo "Last step: ${LAST_STEP:-none}"

env PYTHONUNBUFFERED=1 run_step 1 "update_lists" \
  python3 scripts/update_station_lists.py
python3 scripts/update_status.py

env PYTHONUNBUFFERED=1 run_step 2 "download_metadata" \
  python3 scripts/download_metadata_pdfs.py
python3 scripts/update_status.py

env PYTHONUNBUFFERED=1 run_step 3 "refresh_metadata" \
  python3 scripts/refresh_metadata_pdfs.py
python3 scripts/update_status.py

env PYTHONUNBUFFERED=1 run_step 4 "build_station_table" \
  python3 scripts/build_station_table.py
python3 scripts/update_status.py

env PYTHONUNBUFFERED=1 run_step 5 "setup_database" \
  python3 scripts/setup_database.py
python3 scripts/update_status.py

env PYTHONUNBUFFERED=1 run_step 6 "extract_equipment" \
  python3 scripts/extract_equipment_history.py
python3 scripts/update_status.py

env PYTHONUNBUFFERED=1 run_step 7 "setup_equipment" \
  python3 scripts/setup_database.py --skip-stations
python3 scripts/update_status.py

env PYTHONUNBUFFERED=1 run_step 8 "download_zips" \
  python3 scripts/station_data_downloader.py --verbose
python3 scripts/update_status.py

env PYTHONUNBUFFERED=1 run_step 9 "load_daily_data" \
  python3 scripts/load_daily_data.py --delete-bad-zips --redownload-bad-zips
python3 scripts/update_status.py
