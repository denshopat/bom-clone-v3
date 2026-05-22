# bom-clone-v3

A local pipeline for building the BOM clone database: station metadata, equipment history, and daily rainfall/max/min temperature downloads.

## What it scrapes

Three things from <http://www.bom.gov.au>, all publicly accessible:

1. **Station lists** — `alphaAUS_3.txt` (temperature stations) and `numAUS_139.txt`
   (rainfall stations). The master enumeration of every BOM station with basic
   metadata.
2. **Station metadata PDFs** — `IDCJMD0040.{station}.SiteInfo.pdf` per station.
   Contains site details (lat/lon, elevation, opened/closed dates, district)
   and the full equipment install/remove/replace history.
3. **Daily observation zips** — one per station × product (rainfall, max temp,
   min temp). Each zip holds all available years of daily readings as a CSV.

All traffic is outbound HTTPS to `bom.gov.au`. The scraper sleeps between
requests by default and does not parallelise.

## What it builds

A local PostgreSQL database (`bom_clone_v3`) with these tables:

| Table / view | Contents |
|---|---|
| `station` | Per-station metadata: id, name, coordinates, state, elevation, barometer height, operating years, status, district. |
| `station_equipment_event` | Per-instrument install / remove / replace / share event, with date and source PDF. |
| `station_equipment_element` | Instrument categories (rainfall, thermometer, etc.) present at each station. |
| `daily_rainfall` | One row per station-day: `rainfall_amount`, `rainfall_period`, quality flag. |
| `daily_max_temperature` | One row per station-day: `max_temperature`, accumulation days, quality flag. |
| `daily_min_temperature` | One row per station-day: `min_temperature`, accumulation days, quality flag. |
| `acornsat` (view) | Subset of `station` filtered to BOM's ACORNSAT reference network. |

Plus, on disk in `data/output/`:

- `station_table.csv` / `station_table_known_state.csv` — flat station export
- `station_equipment_events.csv` / `station_equipment_elements.csv` — equipment history

And browsable artifacts in `data/logs/`:

- `status.html` — pipeline run state, auto-refreshing
- `analytics/analytics.html` — yearly row / station counts with charts
- `summary_YYYYMMDD_HHMMSS.{json,txt}` — timestamped DB-size snapshots

## Layout

- `config.ini` - single config file (DB + paths)
- `scripts/` - active scripts
- `sql/` - schema + table definitions
- `data/metadata/` - station metadata PDFs
- `data/lists/` - BOM station lists (`alphaAUS_3.txt`, `numAUS_139.txt`)
- `data/output/` - generated CSV outputs
- `data/logs/` - run logs and error reports
- `data/zips/` - downloaded BOM data zips

## Quick start

```bash
git clone git@github.com:denshopat/bom-clone-v3.git
cd bom-clone-v3
cp config.ini.example config.ini
# edit config.ini (DB creds + paths)
./scripts/run_all.sh
```

## Workflow (end-to-end)

At a high level, we start from the official BOM station lists (temperature + rainfall). Those lists tell us which stations exist and provide basic metadata. We then download each station’s metadata PDF and scrape it to build the station table and the equipment history. The equipment history determines which stations have temperature sensors (and when), which in turn tells us which daily datasets to download. Finally, we download the daily rainfall/max/min temperature zips and load them into the database using a deduped loader.

This project follows a simple, ordered pipeline. Each step builds the inputs for the next:

1. update_lists — download the latest station list files from BOM
2. download_metadata — fetch station metadata PDFs
3. refresh_metadata — clean out corrupt metadata PDFs
4. build_station_table — generate station table CSVs
5. setup_database — create DB + load station/equipment tables
6. extract_equipment — parse equipment history into CSVs
7. setup_equipment — load equipment CSVs + indexes/views
8. download_zips — download daily rainfall/max/min data zips
9. load_daily_data — extract zips and load into daily tables (deduped)

Follow these steps in order. Run commands from the repo root:

```bash
git clone git@github.com:denshopat/bom-clone-v3.git
cd bom-clone-v3
```

### 1) Update station lists

```bash
python3 scripts/update_station_lists.py
```

Flags:
- `--output-dir PATH` destination for list files (default: `data/lists`)
- `--timeout SECONDS` HTTP timeout per request

### 2) Download station metadata PDFs

```bash
python3 scripts/download_metadata_pdfs.py
```

Flags:
- `--metadata-dir PATH` destination for PDFs (default: `data/metadata`)
- `--log-file PATH` CSV log for failed downloads
- `--sleep SECONDS` delay between downloads
- `--limit N` cap number of stations to fetch

If you need to clean metadata PDFs (remove corrupt or unreadable files):

```bash
python3 scripts/refresh_metadata_pdfs.py
```

Flags:
- `--metadata-dir PATH` location of PDFs to verify
- `--write-errors PATH` CSV log for failed re-downloads
- `--sleep SECONDS` delay between downloads
- `--limit N` cap number of re-downloads

### 3) Build station table CSV

```bash
python3 scripts/build_station_table.py
```

Output: `data/output/station_table.csv` and `data/output/station_table_known_state.csv`

Flags:
- `--download-missing` try to fetch missing metadata PDFs
- `--download-limit N` cap missing-PDF downloads
- `--download-sleep SECONDS` delay between missing-PDF downloads
- `--output PATH` output CSV path

### 4) Setup database and load station/equipment tables

Automated (recommended):

```bash
python3 scripts/setup_database.py
```

Flags:
- `--database NAME` override DB name from `config.ini`
- `--schema PATH` schema SQL file to load
- `--station-csv PATH` station CSV to load
- `--events-csv PATH` equipment events CSV
- `--elements-csv PATH` equipment elements CSV
- `--equipment-sql PATH` equipment table SQL file
- `--skip-stations` do not load station table
- `--skip-equipment` do not load equipment tables
- `--skip-indexes` skip equipment indexes/views

### 5) Extract equipment history

```bash
python3 scripts/extract_equipment_history.py
```

Flags:
- `--metadata-dir PATH` source PDFs directory
- `--events-out PATH` output events CSV
- `--elements-out PATH` output elements CSV
- `--errors-out PATH` CSV log for parse errors

### 6) Download daily rainfall/max/min zips

```bash
python3 scripts/station_data_downloader.py --verbose
```

Flags:
- `--database NAME` override DB name from `config.ini`
- `--download-dir PATH` destination for zips
- `--log-file PATH` CSV log for downloads
- `--sleep SECONDS` delay between downloads
- `--limit N` cap total download attempts
- `--dry-run` print planned downloads without fetching
- `--no-resume` ignore prior log state
- `--verbose` print per-download decisions

Downloads go to `data/zips/` (from `config.ini`).

### 7) Extract + load daily data into DB (deduped)

This loader uses staging tables and unique indexes, so it is safe to re-run.

```bash
python3 scripts/load_daily_data.py --delete-bad-zips --redownload-bad-zips
```

Flags:
- `--extract-only` only extract zips, skip DB load
- `--load-only` only load extracted CSVs
- `--delete-bad-zips` remove corrupt zips during extract
- `--redownload-bad-zips` re-download corrupt zips and re-extract

### 8) Optional clean restart for daily data

```bash
psql -d bom_clone_v3 -c \"TRUNCATE daily_rainfall, daily_max_temperature, daily_min_temperature RESTART IDENTITY;\"
```

## Notes

- `scripts/station_data_downloader.py` uses equipment tables in `bom_clone_v3` to determine which stations have temperature data.
- Logs are written to `data/logs/`.

## One-shot runner

To run the full workflow in order (including downloads and DB load):

```bash
./scripts/run_all.sh
```

This script is intentionally sequential; review it before running.

### Resume-aware runner

`run_all.sh` stores progress in `data/logs/run_state.env` and skips completed steps by default.

Examples:

- Run from the beginning (default):
  ```bash
  ./scripts/run_all.sh
  ```

- Start from a specific step:
  ```bash
  ./scripts/run_all.sh --from 6
  ```

- Stop after a step:
  ```bash
  ./scripts/run_all.sh --to 8
  ```

- Force a single step to re-run (even if already completed):
  ```bash
  ./scripts/run_all.sh --force 8
  ```

- Reset the state file and run everything:
  ```bash
  ./scripts/run_all.sh --reset
  ```

- Show current status:
  ```bash
  ./scripts/run_all.sh --status
  ```

Step map:

1. update_lists  
2. download_metadata  
3. refresh_metadata  
4. build_station_table  
5. setup_database  
6. extract_equipment  
7. setup_equipment  
8. download_zips  
9. load_daily_data

## Status dashboard

A lightweight status dashboard is generated at `data/logs/status.html` and auto-refreshes every 30 seconds.

Generate + open it:

```bash
./scripts/open_status.sh
```

Or update without opening:

```bash
python3 scripts/update_status.py
```

## Summary reports

Generate a timestamped summary snapshot (useful if logs are rotated/deleted):

```bash
python3 scripts/summary_report.py
```

Outputs:
- `data/logs/summary_YYYYMMDD_HHMMSS.json`
- `data/logs/summary_YYYYMMDD_HHMMSS.txt`

## Current temperature quick update

This flow targets only stations that are already current in the daily temp tables
(based on the global max dates in `daily_max_temperature` and `daily_min_temperature`).
It refreshes just those max/min zips and reloads only the temp tables.

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

Notes:
- `--force` re-downloads temp zips even if they already exist.
- `--force-extract` re-extracts CSVs even if already present.
- Use `--either` on the downloader if you want stations current in max OR min.

## Analytics dashboard

Generates a post-run analytics page with embedded charts:

```bash
python3 scripts/analytics_dashboard.py
```

Open it in your browser:

```bash
./scripts/open_analytics.sh
```

Outputs:
- `data/logs/analytics/analytics.html`
- `data/logs/analytics/analytics.json`

## Data source and attribution

All raw data is sourced from the Australian Bureau of Meteorology
(<http://www.bom.gov.au>). This project is an unaffiliated mirror; it does not
modify BOM data semantically, only stores and indexes it locally. Respect the
BOM's terms of use when redistributing observations.

## Security and privacy

- The only secret used by this project is your local PostgreSQL password,
  stored in `config.ini`. That file is gitignored and is never required to
  be shared; `config.ini.example` shows the expected layout.
- All network traffic is outbound HTTPS to `bom.gov.au`. No inbound network
  surface, no API tokens, no telemetry.
- The data itself contains no personal information — only weather station
  metadata (location, equipment) and daily observations.

## License

Released under the [MIT License](LICENSE).
