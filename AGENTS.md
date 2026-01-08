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
- `scripts/download_current_temps.py` → downloads current-station max/min temp zips + writes station list

## Database
- Target DB: `bom_clone_v3`
- Station table loads from `data/output/station_table_known_state.csv` (state is required).

## Current temperature quick update
Use this when you only want to refresh max/min temperature data for stations that are
already current in the temp tables (based on the global max dates).

1) Download current-station max/min zips and write the station list:
   ```bash
   python3 scripts/download_current_temps.py --force
   ```

2) Extract + load only max/min temps for that station list:
   ```bash
   python3 scripts/load_daily_data.py \
     --stations-file data/output/current_temp_stations.txt \
     --data-types daily_max_temperature,daily_min_temperature \
     --force-extract
   ```

Or run the wrapper:
   ```bash
   ./scripts/update_current_temps.sh
   ```

## Git Hygiene
- Never commit `config.ini` or large data directories under `data/`.
- Use `config.ini.example` for sharing config layout.

## SQL Schema Prompt (copy/paste)
Use this schema snapshot when asking ChatGPT to help write SQL queries:

```
Database: bom_clone_v3

public.station
- id (integer, PK, identity)
- bom_station_number (integer, not null)
- dist (integer)
- station_name (varchar(100), not null)
- start_year (integer)
- end_year (integer)
- latitude (double precision)
- longitude (double precision)
- source (varchar(30))
- state (varchar(3), not null)
- height (double precision)
- bar_height (double precision)
- wmo (integer)
- metadata_compiled (date)
- bom_district_name (text)
- identification (varchar(30))
- network_classification (varchar(100))
- station_purpose (varchar(100))
- aws (varchar(30))
- status (varchar(20))
- note (varchar(50))

public.station_equipment_event
- id (integer, PK, identity)
- bom_station_number (integer, not null)
- element (text, not null)
- action (varchar(10))
- instrument_detail (text)
- system (text)
- event_date (date)
- source_pdf (text)

public.station_equipment_element
- id (integer, PK, identity)
- bom_station_number (integer, not null)
- element (text, not null)
- has_events (varchar(1))
- source_pdf (text)

public.acornsat (view)
- View on `public.station` containing BOM ACORNSAT network stations.
- Same columns as `public.station`.

public.daily_rainfall
- id (integer, PK, identity)
- bom_station_number (integer, not null)
- date (date, not null)
- rainfall_amount (numeric(6,2))
- rainfall_period (integer)
- quality (boolean)
- product_code (product_code_enum, not null)

public.daily_max_temperature
- id (integer, PK, identity)
- bom_station_number (integer, not null)
- date (date, not null)
- max_temperature (numeric(4,1))
- accumulation_days (integer)
- quality (boolean)
- product_code (product_code_enum, not null)

public.daily_min_temperature
- id (integer, PK, identity)
- bom_station_number (integer, not null)
- date (date, not null)
- min_temperature (numeric(4,1))
- accumulation_days (integer)
- quality (boolean)
- product_code (product_code_enum, not null)

```
