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

## Quick Start

1) Build station table CSV:

```bash
python3 scripts/build_station_table.py
```

2) Extract equipment history:

```bash
python3 scripts/extract_equipment_history.py
```

3) Download daily data (rainfall/max/min) without Selenium:

```bash
python3 scripts/station_data_downloader.py --limit 50 --verbose
```

## Notes

- `scripts/station_data_downloader.py` uses `station_equipment_*` tables in `bom_clone_v3` to decide which stations have temperature data.
- Logs are written to `data/logs/`.
