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

### 1) Station metadata PDFs (one-time)

- Place BOM station metadata PDFs under `data/metadata/`.
- Place BOM lists in `data/lists/`:
  - `alphaAUS_3.txt` (temperature stations)
  - `numAUS_139.txt` (rainfall stations)

If you need to clean metadata PDFs:

```bash
python3 scripts/refresh_metadata_pdfs.py
```

### 2) Build station table CSV

```bash
python3 scripts/build_station_table.py
```

Output: `data/output/station_table.csv` and `data/output/station_table_known_state.csv`

### 3) Load station table into DB

Automated (recommended):

```bash
python3 scripts/setup_database.py
```

Manual (psql):

```bash
psql -d bom_clone_v3 -f sql/bom_clone_v3_schema.sql
psql -d bom_clone_v3 -c "\\copy station (bom_station_number, station_name, start_year, end_year, latitude, longitude, source, state, height, bar_height, wmo, metadata_compiled, bom_district_name, identification, network_classification, station_purpose, aws, status) FROM 'data/output/station_table_known_state.csv' WITH (FORMAT csv, HEADER true)"
```

### 4) Extract equipment history

```bash
python3 scripts/extract_equipment_history.py
```

Outputs:
- `data/output/station_equipment_events.csv`
- `data/output/station_equipment_elements.csv`

### 5) Load equipment history into DB

Automated (recommended, includes equipment indexes/views):

```bash
python3 scripts/setup_database.py --skip-stations
```

Manual:

```bash
psql -d bom_clone_v3 -f sql/station_equipment_tables.sql
psql -d bom_clone_v3 -c "\\copy station_equipment_event_stage (bom_station_number, element, action, instrument_detail, system, event_date, source_pdf) FROM 'data/output/station_equipment_events.csv' WITH (FORMAT csv, HEADER true)"
psql -d bom_clone_v3 -c \"INSERT INTO station_equipment_event (bom_station_number, element, action, instrument_detail, system, event_date, source_pdf) SELECT bom_station_number::int, element, action, instrument_detail, system, CASE WHEN event_date = '' THEN NULL ELSE to_date(event_date, 'DD/MON/YYYY') END, source_pdf FROM station_equipment_event_stage;\"
psql -d bom_clone_v3 -c \"DROP TABLE station_equipment_event_stage;\"
psql -d bom_clone_v3 -c \"\\copy station_equipment_element (bom_station_number, element, has_events, source_pdf) FROM 'data/output/station_equipment_elements.csv' WITH (FORMAT csv, HEADER true)\"
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
