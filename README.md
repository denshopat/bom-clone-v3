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

Follow these steps in order. Run commands from the repo root:

```bash
cd REPO_ROOT
```

### 1) Update station lists

```bash
python3 scripts/update_station_lists.py
```

### 2) Download station metadata PDFs

```bash
python3 scripts/download_metadata_pdfs.py
```

If you need to clean metadata PDFs (remove corrupt or unreadable files):

```bash
python3 scripts/refresh_metadata_pdfs.py
```

### 3) Build station table CSV

```bash
python3 scripts/build_station_table.py
```

Output: `data/output/station_table.csv` and `data/output/station_table_known_state.csv`

### 4) Setup database and load station/equipment tables

Automated (recommended):

```bash
python3 scripts/setup_database.py
```

### 5) Extract equipment history

```bash
python3 scripts/extract_equipment_history.py
```

### 6) Download daily rainfall/max/min zips

```bash
python3 scripts/station_data_downloader.py --verbose
```

Downloads go to `data/zips/` (from `config.ini`).

### 7) Extract + load daily data into DB (deduped)

This loader uses staging tables and unique indexes, so it is safe to re-run.

```bash
python3 scripts/load_daily_data.py --delete-bad-zips --redownload-bad-zips
```

### 8) Optional clean restart for daily data

```bash
psql -d bom_clone_v3 -c \"TRUNCATE daily_rainfall, daily_max_temperature, daily_min_temperature RESTART IDENTITY;\"
```

## Notes

- `scripts/station_data_downloader.py` uses equipment tables in `bom_clone_v3` to determine which stations have temperature data.
- Logs are written to `data/logs/`.
