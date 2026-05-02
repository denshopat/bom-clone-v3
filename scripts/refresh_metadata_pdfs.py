#!/usr/bin/env python3
import argparse
import contextlib
import io
import csv
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from scrape_station_metadata import extract_text_first_page
from station_list_compare import save_metadata_pdf


def station_number_from_filename(filename):
    parts = filename.split(".")
    if len(parts) < 3:
        return None
    try:
        return int(parts[1])
    except ValueError:
        return None


def is_readable_pdf(pdf_path):
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            _ = extract_text_first_page(pdf_path)
        return True
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Delete zero-byte or unreadable metadata PDFs and re-download."
    )
    parser.add_argument(
        "--metadata-dir",
        default=str(Path(__file__).resolve().parent.parent / "data/metadata"),
        help="Directory containing station metadata PDFs.",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.5,
        help="Seconds to sleep between downloads.",
    )
    parser.add_argument(
        "--write-errors",
        default=str(Path(__file__).resolve().parent.parent / "data/logs/refresh_download_errors.csv"),
        help="CSV path to write download errors.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional limit on number of re-downloads.",
    )
    args = parser.parse_args()

    metadata_dir = Path(args.metadata_dir)
    bad_station_numbers = []

    for pdf_path in metadata_dir.glob("IDCJMD0040.*.SiteInfo.pdf"):
        try:
            size = pdf_path.stat().st_size
        except OSError:
            size = 0

        if size == 0 or not is_readable_pdf(pdf_path):
            station_number = station_number_from_filename(pdf_path.name)
            if station_number is not None:
                bad_station_numbers.append(station_number)
            try:
                pdf_path.unlink()
            except OSError:
                pass

    if args.limit is not None:
        bad_station_numbers = bad_station_numbers[: args.limit]

    download_errors = []
    for station_number in bad_station_numbers:
        ok, err = save_metadata_pdf(station_number, metadata_dir)
        if not ok:
            download_errors.append([station_number, err])

    if args.write_errors:
        with open(args.write_errors, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["station_number", "error"])
            writer.writerows(download_errors)

    print(f"Bad PDFs removed: {len(bad_station_numbers)}")
    print(f"Download errors: {len(download_errors)}")


if __name__ == "__main__":
    main()
