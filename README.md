# bom-clone-v3

A local pipeline for building the BOM clone database: station metadata, equipment history, and daily rainfall/max/min temperature downloads.

## Layout

- `config.ini` - single config file (DB + paths)
- `scripts/` - active scripts
- `scripts/legacy/` - older scripts kept for reference
- `sql/` - schema + table definitions
- `data/metadata/` - station metadata PDFs
- `data/lists/` - BOM station lists (`alphaAUS_3.txt`, `numAUS_139.txt`)
- `data/output/` - generated CSV outputs
- `data/logs/` - run logs and error reports
- `data/zips/` - downloaded BOM data zips

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
- `--output-dir PATH`
- `--timeout SECONDS`

### 2) Download station metadata PDFs

```bash
python3 scripts/download_metadata_pdfs.py
```

Flags:
- `--metadata-dir PATH`
- `--log-file PATH`
- `--sleep SECONDS`
- `--limit N`

If you need to clean metadata PDFs (remove corrupt or unreadable files):

```bash
python3 scripts/refresh_metadata_pdfs.py
```

Flags:
- `--metadata-dir PATH`
- `--write-errors PATH`
- `--sleep SECONDS`
- `--limit N`

### 3) Build station table CSV

```bash
python3 scripts/build_station_table.py
```

Output: `data/output/station_table.csv` and `data/output/station_table_known_state.csv`

Flags:
- `--download-missing`
- `--download-limit N`
- `--download-sleep SECONDS`
- `--output PATH`

### 4) Setup database and load station/equipment tables

Automated (recommended):

```bash
python3 scripts/setup_database.py
```

Flags:
- `--database NAME`
- `--schema PATH`
- `--station-csv PATH`
- `--events-csv PATH`
- `--elements-csv PATH`
- `--equipment-sql PATH`
- `--skip-stations`
- `--skip-equipment`
- `--skip-indexes`

### 5) Extract equipment history

```bash
python3 scripts/extract_equipment_history.py
```

Flags:
- `--metadata-dir PATH`
- `--events-out PATH`
- `--elements-out PATH`
- `--errors-out PATH`

### 6) Download daily rainfall/max/min zips

```bash
python3 scripts/station_data_downloader.py --verbose
```

Flags:
- `--database NAME`
- `--download-dir PATH`
- `--log-file PATH`
- `--sleep SECONDS`
- `--limit N`
- `--dry-run`
- `--no-resume`
- `--verbose`

Downloads go to `data/zips/` (from `config.ini`).

### 7) Extract + load daily data into DB (deduped)

This loader uses staging tables and unique indexes, so it is safe to re-run.

```bash
python3 scripts/load_daily_data.py --delete-bad-zips --redownload-bad-zips
```

Flags:
- `--extract-only`
- `--load-only`
- `--delete-bad-zips`
- `--redownload-bad-zips`

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
