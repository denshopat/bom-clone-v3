#!/usr/bin/env python3
import argparse
import csv
import os
import re
import sys
import time
from pathlib import Path

import psycopg2

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(PROJECT_DIR))

from config import get_db_params, get_paths, load_config
from station_data_downloader import (
    OBS_CODES,
    download_zip,
    fetch_all_years_url,
    load_existing_files,
    load_resume_state,
    resolve_log_file,
    write_log_row,
)


def get_global_temp_dates(conn_params):
    query = """
        SELECT
            (SELECT MAX(date) FROM daily_max_temperature) AS max_date,
            (SELECT MAX(date) FROM daily_min_temperature) AS min_date
    """
    with psycopg2.connect(**conn_params) as conn:
        with conn.cursor() as cursor:
            cursor.execute(query)
            row = cursor.fetchone()
            return row[0], row[1]


def get_current_temp_stations(conn_params, require_both=True):
    max_date, min_date = get_global_temp_dates(conn_params)
    if not max_date or not min_date:
        return set(), max_date, min_date

    if require_both:
        query = """
            SELECT mx.bom_station_number
            FROM (
                SELECT bom_station_number, MAX(date) AS max_date
                FROM daily_max_temperature
                GROUP BY bom_station_number
            ) mx
            JOIN (
                SELECT bom_station_number, MAX(date) AS max_date
                FROM daily_min_temperature
                GROUP BY bom_station_number
            ) mn ON mn.bom_station_number = mx.bom_station_number
            WHERE mx.max_date = %s
              AND mn.max_date = %s
            ORDER BY mx.bom_station_number
        """
        params = (max_date, min_date)
    else:
        query = """
            SELECT DISTINCT bom_station_number
            FROM (
                SELECT bom_station_number
                FROM (
                    SELECT bom_station_number, MAX(date) AS max_date
                    FROM daily_max_temperature
                    GROUP BY bom_station_number
                ) mx
                WHERE mx.max_date = %s
                UNION
                SELECT bom_station_number
                FROM (
                    SELECT bom_station_number, MAX(date) AS max_date
                    FROM daily_min_temperature
                    GROUP BY bom_station_number
                ) mn
                WHERE mn.max_date = %s
            ) current_stations
            ORDER BY bom_station_number
        """
        params = (max_date, min_date)

    with psycopg2.connect(**conn_params) as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            return {row[0] for row in cursor.fetchall()}, max_date, min_date


def remove_existing_files(download_dir, station_number, expected_prefix):
    removed = 0
    for filename in list(os.listdir(download_dir)):
        if (
            filename.endswith(".zip")
            and filename.startswith(expected_prefix)
            and re.search(rf"_{station_number}_", filename)
        ):
            try:
                os.remove(Path(download_dir) / filename)
                removed += 1
            except OSError:
                continue
    return removed


def main():
    parser = argparse.ArgumentParser(
        description="Download latest max/min temp zips for stations current in the DB."
    )
    repo_root = Path(__file__).resolve().parent.parent
    parser.add_argument(
        "--database",
        default=None,
        help="Override database name from config.",
    )
    parser.add_argument(
        "--download-dir",
        default=None,
        help="Override download directory.",
    )
    parser.add_argument(
        "--log-file",
        default=str(repo_root / "data/logs/current_temp_updater.csv"),
        help="Override log file path.",
    )
    parser.add_argument(
        "--stations-out",
        default=str(repo_root / "data/output/current_temp_stations.txt"),
        help="Write current station numbers to this file.",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.5,
        help="Seconds to sleep between downloads.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of downloads (stations).",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Disable resume behavior based on the log file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print planned downloads without fetching.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print skip/download decisions as they happen.",
    )
    parser.add_argument(
        "--either",
        action="store_true",
        help="Include stations current in either max or min tables (default: both).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if a zip already exists.",
    )
    args = parser.parse_args()

    config = load_config()
    conn_params = get_db_params(config)
    if args.database:
        conn_params["database"] = args.database

    paths = get_paths(config)
    download_dir = args.download_dir or paths.get("zip_dir", "./newzips")
    log_file = resolve_log_file(args.log_file)

    os.makedirs(download_dir, exist_ok=True)
    os.makedirs(Path(log_file).parent, exist_ok=True)

    stations, max_date, min_date = get_current_temp_stations(
        conn_params, require_both=not args.either
    )
    if not max_date or not min_date:
        print("No max/min temperature data found in the database.")
        return

    station_list = sorted(stations)
    if args.limit is not None:
        station_list = station_list[: args.limit]

    stations_out = Path(args.stations_out)
    stations_out.parent.mkdir(parents=True, exist_ok=True)
    with open(stations_out, "w", encoding="utf-8") as handle:
        for station_number in station_list:
            handle.write(f"{station_number}\n")

    print(
        f"Current stations: {len(station_list)} "
        f"(max date {max_date}, min date {min_date})"
    )
    print(f"Stations list: {stations_out}")

    existing_files = load_existing_files(download_dir)
    resume_state = {}
    last_downloaded = None
    if not args.no_resume:
        resume_state, last_downloaded = load_resume_state(log_file)

    planned = []
    for station_number in station_list:
        planned.append((station_number, "max_temp"))
        planned.append((station_number, "min_temp"))

    skipped = 0
    downloaded = 0
    no_data = 0
    errors = 0
    dry_runs = 0

    with open(log_file, "a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "station_number",
                "obs_code",
                "status",
                "message",
                "source_url",
                "file_path",
            ],
        )
        if handle.tell() == 0:
            writer.writeheader()

        if last_downloaded:
            redo_station = last_downloaded.get("station_number")
            redo_obs = last_downloaded.get("obs_code")
            redo_path = last_downloaded.get("file_path") or ""
            if redo_path and os.path.exists(redo_path):
                try:
                    os.remove(redo_path)
                except OSError:
                    pass
            if redo_station and redo_obs:
                resume_state.pop((redo_station, redo_obs), None)

        for station_number, category in planned:
            obs_code = OBS_CODES[category]
            if category == "max_temp":
                expected_prefix = "IDCJAC0010"
            else:
                expected_prefix = "IDCJAC0011"

            if args.force:
                removed = remove_existing_files(
                    download_dir, station_number, expected_prefix
                )
                if removed and args.verbose:
                    print(f"removed {removed} existing {station_number} {obs_code}")
                existing_files = load_existing_files(download_dir)

            already_downloaded = any(
                name.startswith(expected_prefix)
                and re.search(rf"_{station_number}_", name)
                for name in existing_files
            )
            resume_key = (str(station_number), obs_code)
            if not args.no_resume and resume_key in resume_state:
                status = resume_state[resume_key].get("status")
                file_path = resume_state[resume_key].get("file_path") or ""
                if file_path and os.path.exists(file_path):
                    try:
                        if os.path.getsize(file_path) == 0:
                            already_downloaded = False
                        else:
                            already_downloaded = True
                    except OSError:
                        already_downloaded = False
                else:
                    already_downloaded = False

                if status in {"downloaded", "skip", "no_data", "error"} and already_downloaded:
                    skipped += 1
                    write_log_row(
                        writer,
                        station_number,
                        obs_code,
                        "skip",
                        f"resume_{status}",
                        "",
                        file_path,
                    )
                    if args.verbose:
                        print(f"skip {station_number} {obs_code} (resume_{status})")
                    continue
            if already_downloaded:
                skipped += 1
                write_log_row(
                    writer,
                    station_number,
                    obs_code,
                    "skip",
                    "already_downloaded",
                    "",
                    "",
                )
                if args.verbose:
                    print(f"skip {station_number} {obs_code} (already_downloaded)")
                continue

            if args.dry_run:
                dry_runs += 1
                print(f"Would fetch {station_number} ({category})")
                write_log_row(
                    writer,
                    station_number,
                    obs_code,
                    "dry_run",
                    "skipped",
                    "",
                    "",
                )
                continue

            try:
                source_url, all_years_url = fetch_all_years_url(
                    station_number, obs_code
                )
            except Exception as exc:
                errors += 1
                write_log_row(
                    writer,
                    station_number,
                    obs_code,
                    "error",
                    f"fetch_failed: {exc}",
                    "",
                    "",
                )
                if args.verbose:
                    print(f"error {station_number} {obs_code} (fetch_failed)")
                continue

            if not all_years_url:
                no_data += 1
                write_log_row(
                    writer,
                    station_number,
                    obs_code,
                    "no_data",
                    "all_years_link_missing",
                    source_url,
                    "",
                )
                if args.verbose:
                    print(f"no_data {station_number} {obs_code}")
                continue

            try:
                zip_path = download_zip(
                    all_years_url, download_dir, station_number, obs_code
                )
                existing_files.add(zip_path.name)
                downloaded += 1
                write_log_row(
                    writer,
                    station_number,
                    obs_code,
                    "downloaded",
                    "",
                    all_years_url,
                    str(zip_path),
                )
                if args.verbose:
                    print(f"downloaded {station_number} {obs_code} -> {zip_path.name}")
            except Exception as exc:
                errors += 1
                write_log_row(
                    writer,
                    station_number,
                    obs_code,
                    "error",
                    f"download_failed: {exc}",
                    all_years_url,
                    "",
                )
                if args.verbose:
                    print(f"error {station_number} {obs_code} (download_failed)")
            time.sleep(args.sleep)

    print(
        "Summary: "
        f"stations={len(station_list)}, planned={len(planned)}, "
        f"downloaded={downloaded}, skipped={skipped}, no_data={no_data}, "
        f"errors={errors}, dry_run={dry_runs}"
    )
    print(f"Log: {log_file}")


if __name__ == "__main__":
    main()
