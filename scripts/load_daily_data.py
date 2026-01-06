#!/usr/bin/env python3
import argparse
import csv
import os
import zipfile
from pathlib import Path

import pandas as pd
from pandas.errors import EmptyDataError
from sqlalchemy import create_engine, text

from config import get_paths, get_sqlalchemy_url, load_config


DATA_TYPES = {
    "daily_rainfall": "09",
    "daily_max_temperature": "10",
    "daily_min_temperature": "11",
}

INSERT_COLUMNS = {
    "daily_rainfall": [
        "bom_station_number",
        "date",
        "product_code",
        "rainfall_amount",
        "rainfall_period",
        "quality",
    ],
    "daily_max_temperature": [
        "bom_station_number",
        "date",
        "product_code",
        "max_temperature",
        "accumulation_days",
        "quality",
    ],
    "daily_min_temperature": [
        "bom_station_number",
        "date",
        "product_code",
        "min_temperature",
        "accumulation_days",
        "quality",
    ],
}


def safe_extract(archive, members, extract_dir):
    for member in members:
        normalized = os.path.normpath(member)
        if normalized.endswith(os.sep):
            continue
        if ".." in normalized.split(os.sep):
            continue
        archive.extract(member, path=extract_dir)


def extract_all_zips(zip_dir, extract_dir, error_log=None, delete_bad=False):
    zip_dir = Path(zip_dir)
    extract_dir = Path(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)

    extracted = 0
    skipped = 0
    bad_zips = 0
    error_rows = []

    for filename in sorted(zip_dir.glob("*_1800.zip")):
        try:
            with zipfile.ZipFile(filename, "r") as archive:
                data_members = [
                    member
                    for member in archive.namelist()
                    if member.endswith("_Data.csv")
                ]
                if not data_members:
                    skipped += 1
                    continue

                needs_extract = False
                for member in data_members:
                    target_path = extract_dir / member
                    if not target_path.exists():
                        needs_extract = True
                        break

                if not needs_extract:
                    skipped += 1
                    continue

                safe_extract(archive, data_members, extract_dir)
                extracted += 1
                print(f"extracted {filename.name}")
        except zipfile.BadZipFile as exc:
            bad_zips += 1
            if error_log:
                error_rows.append([str(filename), "BadZipFile", str(exc)])
            if delete_bad:
                try:
                    filename.unlink()
                except OSError:
                    pass

    if error_log and error_rows:
        with open(error_log, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["zip_path", "error_type", "error"])
            writer.writerows(error_rows)

    print(
        "Extraction summary: "
        f"{extracted} zip(s) unpacked, {skipped} skipped, {bad_zips} bad zip(s)."
    )


def get_column_mapping(table_name):
    column_mappings = {
        "daily_rainfall": {
            "Product code": "product_code",
            "Bureau of Meteorology station number": "bom_station_number",
            "Year": "year",
            "Month": "month",
            "Day": "day",
            "Rainfall amount (millimetres)": "rainfall_amount",
            "Period over which rainfall was measured (days)": "rainfall_period",
            "Quality": "quality",
        },
        "daily_max_temperature": {
            "Product code": "product_code",
            "Bureau of Meteorology station number": "bom_station_number",
            "Year": "year",
            "Month": "month",
            "Day": "day",
            "Maximum temperature (Degree C)": "max_temperature",
            "Days of accumulation of maximum temperature": "accumulation_days",
            "Quality": "quality",
        },
        "daily_min_temperature": {
            "Product code": "product_code",
            "Bureau of Meteorology station number": "bom_station_number",
            "Year": "year",
            "Month": "month",
            "Day": "day",
            "Minimum temperature (Degree C)": "min_temperature",
            "Days of accumulation of minimum temperature": "accumulation_days",
            "Quality": "quality",
        },
    }
    return column_mappings.get(table_name, {})


def ensure_stage_tables(engine):
    stage_tables = {
        "daily_rainfall": "daily_rainfall_stage",
        "daily_max_temperature": "daily_max_temperature_stage",
        "daily_min_temperature": "daily_min_temperature_stage",
    }
    with engine.begin() as conn:
        for target, stage in stage_tables.items():
            conn.execute(
                text(
                    f"CREATE TABLE IF NOT EXISTS {stage} "
                    f"(LIKE {target} INCLUDING DEFAULTS)"
                )
            )
            # Make stage tables nullable for id and drop defaults/constraints.
            conn.execute(text(f"ALTER TABLE {stage} ALTER COLUMN id DROP NOT NULL"))
            conn.execute(text(f"ALTER TABLE {stage} ALTER COLUMN id DROP DEFAULT"))
            conn.execute(text(f"ALTER TABLE {stage} ALTER COLUMN id DROP IDENTITY IF EXISTS"))


def ensure_unique_indexes(engine):
    index_sql = [
        """
        CREATE UNIQUE INDEX IF NOT EXISTS daily_rainfall_unique_idx
        ON daily_rainfall (bom_station_number, date, product_code)
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS daily_max_temperature_unique_idx
        ON daily_max_temperature (bom_station_number, date, product_code)
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS daily_min_temperature_unique_idx
        ON daily_min_temperature (bom_station_number, date, product_code)
        """,
    ]
    with engine.begin() as conn:
        for statement in index_sql:
            conn.execute(text(statement))


def load_station_csv(engine, table, csv_path):
    column_mapping = get_column_mapping(table)
    if not column_mapping:
        return 0

    try:
        chunk_iter = pd.read_csv(csv_path, chunksize=50000)
    except EmptyDataError:
        return 0

    rows_written = 0
    stage_table = f"{table}_stage"
    insert_columns = INSERT_COLUMNS.get(table, [])
    if not insert_columns:
        return 0

    for chunk in chunk_iter:
        chunk.rename(columns=column_mapping, inplace=True)
        chunk["date"] = pd.to_datetime(chunk[["year", "month", "day"]])
        chunk.drop(columns=["year", "month", "day"], inplace=True)
        chunk.to_sql(
            stage_table,
            engine,
            if_exists="append",
            index=False,
            method="multi",
            chunksize=1000,
        )

        with engine.begin() as conn:
            columns_sql = ", ".join(insert_columns)
            conn.execute(
                text(
                    f"""
                    INSERT INTO {table} ({columns_sql})
                    SELECT {columns_sql}
                    FROM {stage_table}
                    ON CONFLICT (bom_station_number, date, product_code)
                    DO NOTHING
                    """
                )
            )
            conn.execute(text(f"TRUNCATE {stage_table}"))

        rows_written += len(chunk)

    return rows_written


def load_all_data(extract_dir, engine):
    extract_dir = Path(extract_dir)
    loaded = 0

    for csv_path in sorted(extract_dir.rglob("*_1800_Data.csv")):
        parts = csv_path.name.split("_")
        if len(parts) < 3:
            continue
        data_type = parts[0][-2:]
        table = None
        for table_name, code in DATA_TYPES.items():
            if code == data_type:
                table = table_name
                break
        if not table:
            continue

        rows = load_station_csv(engine, table, csv_path)
        loaded += rows
        print(f"loaded {rows} rows from {csv_path.name} into {table}")

    print(f"Total rows loaded: {loaded}")


def main():
    parser = argparse.ArgumentParser(
        description="Extract BOM zips and load daily data into the database."
    )
    parser.add_argument(
        "--extract-only",
        action="store_true",
        help="Only extract zips; do not load into the database.",
    )
    parser.add_argument(
        "--load-only",
        action="store_true",
        help="Only load extracted CSVs; do not extract zips.",
    )
    parser.add_argument(
        "--delete-bad-zips",
        action="store_true",
        help="Delete corrupt zip files when detected.",
    )
    parser.add_argument(
        "--redownload-bad-zips",
        action="store_true",
        help="Attempt to re-download corrupt zip files.",
    )
    args = parser.parse_args()

    config = load_config()
    paths = get_paths(config)
    zip_dir = paths.get("zip_dir", "./data/zips")
    extract_dir = paths.get("extract_dir", "./data/extracted")

    bad_zip_paths = []
    if not args.load_only:
        error_log = Path(__file__).resolve().parent.parent / "data/logs/extract_errors.csv"
        extract_all_zips(
            zip_dir,
            extract_dir,
            error_log=error_log,
            delete_bad=args.delete_bad_zips,
        )
        if error_log.exists():
            with open(error_log, "r", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                bad_zip_paths = [row["zip_path"] for row in reader]

    if args.extract_only:
        if args.redownload_bad_zips and bad_zip_paths:
            from station_data_downloader import fetch_all_years_url, download_zip

            for zip_path in bad_zip_paths:
                filename = Path(zip_path).name
                parts = filename.split("_")
                if len(parts) < 3:
                    continue
                product_code = parts[0]
                station_number = parts[1]
                obs_code = None
                for code, product in {
                    "136": "IDCJAC0009",
                    "122": "IDCJAC0010",
                    "123": "IDCJAC0011",
                }.items():
                    if product == product_code:
                        obs_code = code
                        break
                if not obs_code:
                    continue

                try:
                    _, all_years_url = fetch_all_years_url(station_number, obs_code)
                    if not all_years_url:
                        continue
                    download_zip(all_years_url, zip_dir, station_number, obs_code)
                except Exception:
                    continue
            extract_all_zips(
                zip_dir,
                extract_dir,
                error_log=error_log,
                delete_bad=args.delete_bad_zips,
            )
        return

    engine = create_engine(get_sqlalchemy_url(config["Database"]))
    ensure_stage_tables(engine)
    ensure_unique_indexes(engine)
    load_all_data(extract_dir, engine)


if __name__ == "__main__":
    main()
