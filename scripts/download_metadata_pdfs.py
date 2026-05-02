#!/usr/bin/env python3
import argparse
import csv
import sys
import tempfile
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from bom_client import BomFetchError, fetch_metadata_pdf, metadata_pdf_filename
from station_list_compare import parse_station_list


def write_atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", delete=False, dir=path.parent) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def main():
    parser = argparse.ArgumentParser(
        description="Download BOM station metadata PDFs."
    )
    repo_root = Path(__file__).resolve().parent.parent
    parser.add_argument(
        "--alpha-list",
        default=str(repo_root / "data/lists/alphaAUS_3.txt"),
        help="Path to alpha list file.",
    )
    parser.add_argument(
        "--num-list",
        default=str(repo_root / "data/lists/numAUS_139.txt"),
        help="Path to numeric list file.",
    )
    parser.add_argument(
        "--metadata-dir",
        default=str(repo_root / "data/metadata"),
        help="Directory for metadata PDFs.",
    )
    parser.add_argument(
        "--log-file",
        default=str(repo_root / "data/logs/metadata_download_errors.csv"),
        help="CSV log for failures.",
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
        help="Limit number of downloads.",
    )
    args = parser.parse_args()

    metadata_dir = Path(args.metadata_dir)
    metadata_dir.mkdir(parents=True, exist_ok=True)

    alpha_records = parse_station_list(Path(args.alpha_list))
    num_records = parse_station_list(Path(args.num_list))
    stations = sorted({r["site"] for r in alpha_records} | {r["site"] for r in num_records})

    failures = []
    downloaded = 0
    skipped = 0

    if args.limit is not None:
        stations = stations[: args.limit]

    for station_number in stations:
        filename = metadata_pdf_filename(station_number)
        dest_path = metadata_dir / filename

        if dest_path.exists() and dest_path.stat().st_size > 0:
            skipped += 1
            continue
        if dest_path.exists() and dest_path.stat().st_size == 0:
            try:
                dest_path.unlink()
            except OSError:
                pass

        try:
            body = fetch_metadata_pdf(station_number)
        except BomFetchError as exc:
            failures.append([station_number, str(exc)])
            time.sleep(args.sleep)
            continue

        write_atomic(dest_path, body)
        downloaded += 1
        time.sleep(args.sleep)

    if failures:
        Path(args.log_file).parent.mkdir(parents=True, exist_ok=True)
        with open(args.log_file, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["station_number", "error"])
            writer.writerows(failures)

    print(
        f"Metadata download summary: downloaded={downloaded}, skipped={skipped}, "
        f"failed={len(failures)}"
    )
    if failures:
        print(f"Failures logged to {args.log_file}")


if __name__ == "__main__":
    main()
