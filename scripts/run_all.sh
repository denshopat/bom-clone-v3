#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

python3 scripts/update_station_lists.py
python3 scripts/download_metadata_pdfs.py
python3 scripts/refresh_metadata_pdfs.py
python3 scripts/build_station_table.py
python3 scripts/setup_database.py
python3 scripts/extract_equipment_history.py
python3 scripts/setup_database.py --skip-stations
python3 scripts/station_data_downloader.py --verbose
python3 scripts/load_daily_data.py --delete-bad-zips --redownload-bad-zips
