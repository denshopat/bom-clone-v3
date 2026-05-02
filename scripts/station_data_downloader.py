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

from bom_client import (
    BomFetchError,
    BomNotFoundError,
    fetch_observation_zip,
    obs_code_for,
    observation_zip_filename,
)
from config import get_db_params, get_paths, load_config


def parse_station_list(file_path):
    stations = set()
    with open(file_path, "r", encoding="utf-8") as handle:
        lines = handle.readlines()

    start_idx = None
    for idx, line in enumerate(lines):
        if set(line.strip()) == {"-"}:
            start_idx = idx + 1
            break

    if start_idx is None:
        return stations

    for line in lines[start_idx:]:
        line = line.rstrip()
        if not line:
            continue
        match = re.match(r"^\s*(\d+)\s+", line)
        if match:
            stations.add(int(match.group(1)))

    return stations


def get_temperature_stations(conn_params):
    query = """
        SELECT DISTINCT bom_station_number
        FROM station_equipment_element
        WHERE has_events = 'Y'
          AND (
            element ILIKE '%temperature%'
            OR element ILIKE '%thermometer%'
          )
        UNION
        SELECT DISTINCT bom_station_number
        FROM station_equipment_event
        WHERE instrument_detail ILIKE '%thermometer%'
           OR instrument_detail ILIKE '%temperature probe%'
    """
    with psycopg2.connect(**conn_params) as conn:
        with conn.cursor() as cursor:
            cursor.execute(query)
            return {row[0] for row in cursor.fetchall()}


def get_rainfall_stations(conn_params):
    query = """
        SELECT DISTINCT bom_station_number
        FROM station_equipment_element
        WHERE has_events = 'Y'
          AND element = 'Rainfall'
    """
    with psycopg2.connect(**conn_params) as conn:
        with conn.cursor() as cursor:
            cursor.execute(query)
            return {row[0] for row in cursor.fetchall()}


def build_station_sets(alpha_path, num_path, conn_params):
    alpha_stations = parse_station_list(alpha_path)
    num_stations = parse_station_list(num_path)

    temp_from_equipment = get_temperature_stations(conn_params)
    rain_from_equipment = get_rainfall_stations(conn_params)

    temp_stations = set(alpha_stations) | temp_from_equipment
    rain_stations = set(num_stations) | rain_from_equipment

    return temp_stations, rain_stations


def load_existing_files(download_dir):
    existing = set()
    if not os.path.isdir(download_dir):
        return existing
    for filename in os.listdir(download_dir):
        if filename.endswith(".zip"):
            existing.add(filename)
    return existing


def load_resume_state(log_file):
    if not os.path.exists(log_file):
        return {}, None

    with open(log_file, "r", encoding="utf-8") as handle:
        first_line = handle.readline().strip()
        if first_line != "station_number,obs_code,status,message,source_url,file_path":
            return {}, None

    latest = {}
    last_downloaded = None
    with open(log_file, "r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            key = (row.get("station_number"), row.get("obs_code"))
            latest[key] = row
            if row.get("status") == "downloaded":
                last_downloaded = row
    return latest, last_downloaded


def resolve_log_file(log_file):
    if not os.path.exists(log_file):
        return log_file

    with open(log_file, "r", encoding="utf-8") as handle:
        first_line = handle.readline().strip()
    if first_line == "station_number,obs_code,status,message,source_url,file_path":
        return log_file

    log_path = Path(log_file)
    return str(log_path.with_suffix(".csv"))


def write_log_row(writer, station_number, obs_code, status, message, source_url, file_path=""):
    writer.writerow(
        {
            "station_number": station_number,
            "obs_code": obs_code,
            "status": status,
            "message": message,
            "source_url": source_url,
            "file_path": file_path,
        }
    )


def save_observation_zip(station_number, product, download_dir):
    """Fetch a per-station observation zip and write it to download_dir
    using the canonical BOM filename. Returns the destination Path."""
    body = fetch_observation_zip(station_number, product)
    dest = Path(download_dir) / observation_zip_filename(station_number, product)
    dest.write_bytes(body)
    return dest


def main():
    parser = argparse.ArgumentParser(
        description="Download BOM rainfall/max/min data without Selenium."
    )
    repo_root = Path(__file__).resolve().parent.parent
    parser.add_argument(
        "--alpha-list",
        default=str(repo_root / "data/lists/alphaAUS_3.txt"),
        help="Path to alpha list file (temp stations).",
    )
    parser.add_argument(
        "--num-list",
        default=str(repo_root / "data/lists/numAUS_139.txt"),
        help="Path to numeric list file (rainfall stations).",
    )
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
        default=None,
        help="Override log file path.",
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
        help="Limit number of downloads (total).",
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
    args = parser.parse_args()

    config = load_config()
    conn_params = get_db_params(config)
    if args.database:
        conn_params["database"] = args.database

    paths = get_paths(config)
    download_dir = args.download_dir or paths.get("zip_dir", "./newzips")
    log_file = args.log_file or paths.get("download_log", "./updater.log")
    log_file = resolve_log_file(log_file)

    os.makedirs(download_dir, exist_ok=True)
    os.makedirs(Path(log_file).parent, exist_ok=True)

    temp_stations, rain_stations = build_station_sets(
        args.alpha_list, args.num_list, conn_params
    )

    existing_files = load_existing_files(download_dir)
    resume_state = {}
    last_downloaded = None
    if not args.no_resume:
        resume_state, last_downloaded = load_resume_state(log_file)

    planned = []
    for station_number in sorted(rain_stations):
        planned.append((station_number, "rainfall"))
    for station_number in sorted(temp_stations):
        planned.append((station_number, "max_temp"))
        planned.append((station_number, "min_temp"))

    if args.limit is not None:
        planned = planned[: args.limit]

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

        for station_number, product in planned:
            obs_code = obs_code_for(product)
            expected_filename = observation_zip_filename(station_number, product)
            expected_prefix = expected_filename.split("_", 1)[0]

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
                print(f"Would fetch {station_number} ({product})")
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
                zip_path = save_observation_zip(station_number, product, download_dir)
            except BomNotFoundError as exc:
                no_data += 1
                write_log_row(
                    writer,
                    station_number,
                    obs_code,
                    "no_data",
                    "all_years_link_missing",
                    "",
                    "",
                )
                if args.verbose:
                    print(f"no_data {station_number} {obs_code}")
                continue
            except BomFetchError as exc:
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

            existing_files.add(zip_path.name)
            downloaded += 1
            write_log_row(
                writer,
                station_number,
                obs_code,
                "downloaded",
                "",
                "",
                str(zip_path),
            )
            if args.verbose:
                print(f"downloaded {station_number} {obs_code} -> {zip_path.name}")
            time.sleep(args.sleep)

    print(
        "Summary: "
        f"planned={len(planned)}, downloaded={downloaded}, "
        f"skipped={skipped}, no_data={no_data}, errors={errors}, "
        f"dry_run={dry_runs}"
    )
    print(f"Log: {log_file}")


if __name__ == "__main__":
    main()
