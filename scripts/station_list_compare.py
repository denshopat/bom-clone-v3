#!/usr/bin/env python3
import argparse
import contextlib
import io
import json
import re
import sys
import time
from pathlib import Path
import csv

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from bom_client import (
    BomFetchError,
    fetch_metadata_pdf,
    metadata_pdf_filename,
)


LIST_LINE_WITH_OBS_RE = re.compile(
    r"^\s*(\d+)\s+(.+?)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+"
    r"([A-Za-z]{3}\s+\d{4})\s+([A-Za-z]{3}\s+\d{4})\s+"
    r"([\d\.]+)\s+(\d+)\s+([\d\.]+)\s*([YN])?\s*$"
)

LIST_LINE_NO_OBS_RE = re.compile(
    r"^\s*(\d+)\s+(.+?)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+"
    r"([A-Za-z]{3}\s+\d{4})\s+([A-Za-z]{3}\s+\d{4})\s+"
    r"([\d\.]+)\s+(\d+)\s*([YN])?\s*$"
)


def parse_station_list(file_path):
    records = []
    with open(file_path, "r", encoding="utf-8") as handle:
        lines = handle.readlines()

    start_idx = None
    has_obs = False
    for idx, line in enumerate(lines):
        if line.strip().startswith("Site") and "Obs" in line:
            has_obs = True
        if set(line.strip()) == {"-"}:
            start_idx = idx + 1
            break

    if start_idx is None:
        raise ValueError(f"Could not find data separator line in {file_path}")

    for line in lines[start_idx:]:
        line = line.rstrip()
        if not line:
            continue
        if has_obs:
            match = LIST_LINE_WITH_OBS_RE.match(line)
            if not match:
                continue
            records.append(
                {
                    "site": int(match.group(1)),
                    "name": match.group(2).strip(),
                    "lat": float(match.group(3)),
                    "lon": float(match.group(4)),
                    "start": match.group(5),
                    "end": match.group(6),
                    "years": float(match.group(7)),
                    "percent": int(match.group(8)),
                    "obs": float(match.group(9)),
                    "aws": match.group(10) or "",
                }
            )
        else:
            match = LIST_LINE_NO_OBS_RE.match(line)
            if not match:
                continue
            records.append(
                {
                    "site": int(match.group(1)),
                    "name": match.group(2).strip(),
                    "lat": float(match.group(3)),
                    "lon": float(match.group(4)),
                    "start": match.group(5),
                    "end": match.group(6),
                    "years": float(match.group(7)),
                    "percent": int(match.group(8)),
                    "obs": None,
                    "aws": match.group(9) or "",
                }
            )

    return records


def collect_pdf_station_numbers(metadata_dir):
    station_numbers = set()
    for pdf_path in metadata_dir.glob("IDCJMD0040.*.SiteInfo.pdf"):
        parts = pdf_path.name.split(".")
        if len(parts) < 3:
            continue
        try:
            station_numbers.add(int(parts[1]))
        except ValueError:
            continue
    return station_numbers


def save_metadata_pdf(station_number, dest_dir):
    """Fetch a metadata PDF and write it to dest_dir.
    Returns (ok, error_message). The caller decides what to do with errors."""
    try:
        body = fetch_metadata_pdf(station_number)
    except BomFetchError as exc:
        return False, str(exc)
    dest_path = Path(dest_dir) / metadata_pdf_filename(station_number)
    dest_path.write_bytes(body)
    return True, ""


def main():
    base_dir = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(
        description="Compare BOM station lists to local metadata PDFs."
    )
    parser.add_argument(
        "--alpha-list",
        default=str(base_dir / "data/lists/alphaAUS_3.txt"),
        help="Path to alpha list file.",
    )
    parser.add_argument(
        "--num-list",
        default=str(base_dir / "data/lists/numAUS_139.txt"),
        help="Path to numeric list file.",
    )
    parser.add_argument(
        "--metadata-dir",
        default=str(base_dir / "data/metadata"),
        help="Directory containing station metadata PDFs.",
    )
    parser.add_argument(
        "--write-missing",
        default=None,
        help="Optional path to write missing station numbers as JSON.",
    )
    parser.add_argument(
        "--write-extra",
        default=None,
        help="Optional path to write extra station numbers as JSON.",
    )
    parser.add_argument(
        "--write-list-csv",
        default=None,
        help="Optional path to write combined station list CSV (number, name, state).",
    )
    parser.add_argument(
        "--write-extra-csv",
        default=None,
        help="Optional path to write extra metadata stations CSV (number, name).",
    )
    parser.add_argument(
        "--write-pdf-errors",
        default=None,
        help="Optional path to write PDF parse errors as CSV.",
    )
    parser.add_argument(
        "--download-missing",
        action="store_true",
        help="Attempt to download missing metadata PDFs.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of missing PDFs to download.",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.5,
        help="Seconds to sleep between downloads.",
    )
    args = parser.parse_args()

    alpha_path = Path(args.alpha_list)
    num_path = Path(args.num_list)
    metadata_dir = Path(args.metadata_dir)

    alpha_records = parse_station_list(alpha_path)
    num_records = parse_station_list(num_path)

    alpha_sites = {r["site"] for r in alpha_records}
    num_sites = {r["site"] for r in num_records}
    combined_sites = sorted(alpha_sites | num_sites)

    existing_sites = collect_pdf_station_numbers(metadata_dir)
    missing_sites = [s for s in combined_sites if s not in existing_sites]
    extra_sites = [s for s in sorted(existing_sites) if s not in combined_sites]

    summary = {
        "alpha_count": len(alpha_sites),
        "num_count": len(num_sites),
        "combined_count": len(combined_sites),
        "existing_metadata_count": len(existing_sites),
        "missing_metadata_count": len(missing_sites),
        "extra_metadata_count": len(extra_sites),
    }

    print(json.dumps(summary, indent=2, ensure_ascii=True))

    if missing_sites:
        print("\nMissing metadata station numbers:")
        for site in missing_sites[:50]:
            print(site)
        if len(missing_sites) > 50:
            print(f"... ({len(missing_sites) - 50} more)")

    if extra_sites:
        print("\nMetadata PDFs not in lists:")
        for site in extra_sites[:50]:
            print(site)
        if len(extra_sites) > 50:
            print(f"... ({len(extra_sites) - 50} more)")

    if args.write_missing:
        Path(args.write_missing).write_text(
            json.dumps(missing_sites, indent=2, ensure_ascii=True) + "\n"
        )
    if args.write_extra:
        Path(args.write_extra).write_text(
            json.dumps(extra_sites, indent=2, ensure_ascii=True) + "\n"
        )
    if args.write_list_csv:
        combined_by_site = {}
        for record in num_records:
            combined_by_site[record["site"]] = record["name"]
        for record in alpha_records:
            combined_by_site[record["site"]] = record["name"]

        with open(args.write_list_csv, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["station_number", "station_name", "state"])
            for site in sorted(combined_by_site):
                writer.writerow([site, combined_by_site[site], ""])
    if args.write_extra_csv:
        from scrape_station_metadata import extract_text, parse_station_metadata

        error_rows = []
        with open(args.write_extra_csv, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["station_number", "station_name"])
            for site in extra_sites:
                pdf_name = metadata_pdf_filename(site)
                pdf_path = metadata_dir / pdf_name
                station_name = ""
                if pdf_path.exists():
                    try:
                        with contextlib.redirect_stderr(io.StringIO()):
                            text = extract_text(pdf_path)
                        record = parse_station_metadata(text)
                        station_name = record.get("station_name") or ""
                    except Exception as exc:
                        station_name = ""
                        if args.write_pdf_errors:
                            error_rows.append([site, str(pdf_path), str(exc)])
                writer.writerow([site, station_name])
        if args.write_pdf_errors:
            with open(args.write_pdf_errors, "w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(["station_number", "pdf_path", "error"])
                writer.writerows(error_rows)

    if args.download_missing:
        to_download = missing_sites
        if args.limit is not None:
            to_download = to_download[: args.limit]

        print("\nDownloading missing metadata PDFs:")
        for site in to_download:
            ok, err = save_metadata_pdf(site, metadata_dir)
            if ok:
                print(f"{site}: ok")
            else:
                print(f"{site}: failed ({err})")
            time.sleep(args.sleep)


if __name__ == "__main__":
    main()
