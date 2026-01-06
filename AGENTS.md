# AGENTS.md

## Purpose
This repo builds and maintains a BOM clone database (stations, equipment history, and daily rainfall/max/min temperature data).

## Project Roots
- Repo root: `REPO_ROOT`
- Station metadata PDFs: `data/metadata/`
- BOM station lists: `data/lists/alphaAUS_3.txt`, `data/lists/numAUS_139.txt`
- Downloaded zips: `data/zips/`
- Logs and error reports: `data/logs/`
- SQL schemas: `sql/`

## Config
- `config.ini` is local-only (contains DB password). Do not commit.
- `config.ini.example` is safe for Git.

## Key Scripts
- `scripts/build_station_table.py` → builds `data/output/station_table.csv`
- `scripts/extract_equipment_history.py` → builds equipment CSVs in `data/output/`
- `scripts/station_data_downloader.py` → downloads daily rainfall/max/min data

## Database
- Target DB: `bom_clone_v3`
- Station table loads from `data/output/station_table_known_state.csv` (state is required).

## Git Hygiene
- Never commit `config.ini` or large data directories under `data/`.
- Use `config.ini.example` for sharing config layout.

