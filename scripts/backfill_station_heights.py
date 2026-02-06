#!/usr/bin/env python3
import argparse
import contextlib
import csv
import io
import sys
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from config import get_db_params, load_config
from scrape_station_metadata import extract_text_first_page, parse_station_metadata
from station_list_compare import station_number_to_pdf_name


def read_metadata_record(pdf_path):
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            text = extract_text_first_page(pdf_path)
        return parse_station_metadata(text)
    except Exception:
        return {}


def normalize_value(value):
    if value is None:
        return ""
    return str(value)


def backfill_csv_rows(rows, metadata_dir, *, overwrite=False):
    updates = []
    updated_rows = []

    for row in rows:
        station_number = row["bom_station_number"]
        try:
            station_number_int = int(station_number)
        except (TypeError, ValueError):
            updated_rows.append(row)
            continue
        height_missing = row.get("height", "").strip() == ""
        bar_height_missing = row.get("bar_height", "").strip() == ""

        if not overwrite and not height_missing and not bar_height_missing:
            updated_rows.append(row)
            continue

        pdf_path = metadata_dir / station_number_to_pdf_name(station_number_int)
        if not pdf_path.exists():
            updated_rows.append(row)
            continue

        metadata = read_metadata_record(pdf_path)
        height = metadata.get("height")
        bar_height = metadata.get("bar_height")

        if height is not None and (overwrite or height_missing):
            row["height"] = normalize_value(height)
        if bar_height is not None and (overwrite or bar_height_missing):
            row["bar_height"] = normalize_value(bar_height)

        if (height is not None and (overwrite or height_missing)) or (
            bar_height is not None and (overwrite or bar_height_missing)
        ):
            updates.append(
                (
                    station_number_int,
                    height if height is not None else None,
                    bar_height if bar_height is not None else None,
                )
            )

        updated_rows.append(row)

    return updated_rows, updates


def update_database(db_params, updates, *, overwrite=False):
    if not updates:
        return 0

    with psycopg2.connect(**db_params) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TEMP TABLE station_height_updates (
                    bom_station_number integer PRIMARY KEY,
                    height double precision,
                    bar_height double precision
                ) ON COMMIT DROP;
                """
            )
            execute_values(
                cur,
                """
                INSERT INTO station_height_updates (bom_station_number, height, bar_height)
                VALUES %s
                ON CONFLICT (bom_station_number) DO UPDATE
                SET height = EXCLUDED.height,
                    bar_height = EXCLUDED.bar_height;
                """,
                updates,
            )
            if overwrite:
                cur.execute(
                    """
                    UPDATE station s
                    SET height = COALESCE(u.height, s.height),
                        bar_height = COALESCE(u.bar_height, s.bar_height)
                    FROM station_height_updates u
                    WHERE s.bom_station_number = u.bom_station_number;
                    """
                )
            else:
                cur.execute(
                    """
                    UPDATE station s
                    SET height = COALESCE(s.height, u.height),
                        bar_height = COALESCE(s.bar_height, u.bar_height)
                    FROM station_height_updates u
                    WHERE s.bom_station_number = u.bom_station_number;
                    """
                )
        conn.commit()

    return len(updates)


def main():
    repo_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(
        description="Backfill station height and barometer height from metadata PDFs."
    )
    parser.add_argument(
        "--input",
        default=str(repo_root / "data/output/station_table_known_state.csv"),
        help="Input station table CSV.",
    )
    parser.add_argument(
        "--output",
        default=str(repo_root / "data/output/station_table_known_state.csv"),
        help="Output station table CSV.",
    )
    parser.add_argument(
        "--metadata-dir",
        default=str(repo_root / "data/metadata"),
        help="Directory containing station metadata PDFs.",
    )
    parser.add_argument(
        "--update-db",
        action="store_true",
        help="Update the station table in the database for missing heights.",
    )
    parser.add_argument(
        "--overwrite-existing",
        action="store_true",
        help="Overwrite existing height values when metadata provides a value.",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    metadata_dir = Path(args.metadata_dir)

    with input_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = reader.fieldnames

    if not fieldnames:
        raise SystemExit("Input CSV has no headers.")

    updated_rows, updates = backfill_csv_rows(
        rows, metadata_dir, overwrite=args.overwrite_existing
    )

    tmp_path = output_path.with_suffix(".tmp")
    with tmp_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(updated_rows)
    tmp_path.replace(output_path)

    if args.update_db:
        config = load_config()
        db_params = get_db_params(config)
        updated = update_database(db_params, updates, overwrite=args.overwrite_existing)
        print(f"db_updates: {updated}")

    print(f"csv_updates: {len(updates)}")
    print(f"output: {output_path}")


if __name__ == "__main__":
    main()
