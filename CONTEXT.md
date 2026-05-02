# Project vocabulary

Canonical terms for this codebase. Use these names in code, comments, and architecture discussions. If you find yourself reaching for a synonym, add the term here instead.

## Domain

- **BOM** — the Australian Bureau of Meteorology (`bom.gov.au`), the upstream this project mirrors.
- **Station** — a BOM weather observation station, identified by an integer `bom_station_number`. Has metadata (location, height, status), equipment history, and daily observations.
- **Station list** — one of two plaintext files BOM publishes that enumerate stations and basic metadata: `alphaAUS_3.txt` (temperature stations) and `numAUS_139.txt` (rainfall stations). Has a fixed-format tabular body after a `---` separator.
- **Station metadata PDF** — per-station `IDCJMD0040.{nnnnnn}.SiteInfo.pdf` containing detailed metadata (lat/lon, elevation, opened/closed dates, etc.) and equipment install/remove history. Filename convention is canonical.
- **Daily observation** — one station-day reading. Three kinds: rainfall, maximum temperature, minimum temperature. Stored in `daily_rainfall`, `daily_max_temperature`, `daily_min_temperature`.
- **Observation zip** — the per-station, per-product zip BOM serves on demand, containing all years of daily observations as a CSV. Reached via a two-step flow: fetch a dataFile landing page, scrape the "All years of data" link, fetch the zip.
- **Product** — one of `rainfall`, `max_temp`, `min_temp`. Maps to a BOM observation code (`136`, `122`, `123`) and a product code prefix (`IDCJAC0009`, `IDCJAC0010`, `IDCJAC0011`).
- **Equipment event** — an install / remove / replace / share / unshare action against a station's instrument, with a date and source PDF. Parsed out of station metadata PDFs.
- **Equipment element** — a category of instrument present at a station (e.g. "Rainfall", "Thermometer"). Has a `has_events` flag indicating whether any equipment events exist for it.

## Architecture

- **BOM client** — `scripts/bom_client.py`. The single module that owns network I/O against `bom.gov.au`. Three operations: `fetch_station_list`, `fetch_metadata_pdf`, `fetch_observation_zip`. Returns bytes; raises typed exceptions (`BomFetchError`, `BomValidationError`, `BomNotFoundError`) on failure. Also owns BOM filename conventions (`metadata_pdf_filename`, `observation_zip_filename`, `product_from_zip_filename`). Does not own retries, courtesy sleeps, or "skip if already on disk" — those live in the orchestration layer. Test seam: monkeypatch `bom_client._http_get`.
