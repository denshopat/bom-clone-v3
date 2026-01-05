#!/usr/bin/env python3
import argparse
import contextlib
import csv
import io
import json
import re
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from scrape_station_metadata import extract_text_first_page, parse_station_metadata
from station_list_compare import (
    collect_pdf_station_numbers,
    download_metadata_pdf,
    parse_station_list,
    station_number_to_pdf_name,
)


MONTH_YEAR_RE = re.compile(r"^[A-Za-z]{3}\s+(\d{4})$")


def year_from_month_year(value):
    if not value:
        return None
    match = MONTH_YEAR_RE.match(value.strip())
    if not match:
        return None
    return int(match.group(1))


def normalize_aws(value):
    if not value:
        return None
    value = value.strip().upper()
    if value in {"Y", "N"}:
        return value
    if value in {"YES", "NO"}:
        return "Y" if value == "YES" else "N"
    return None


def choose(*values):
    for value in values:
        if value is not None and value != "":
            return value
    return None


def load_list_records(alpha_path, num_path):
    alpha_records = parse_station_list(alpha_path)
    num_records = parse_station_list(num_path)

    combined = {}
    for record in num_records:
        combined[record["site"]] = record

    for record in alpha_records:
        combined[record["site"]] = {
            **combined.get(record["site"], {}),
            **record,
        }

    return alpha_records, num_records, combined


def read_metadata_record(pdf_path, pdf_errors=None):
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            text = extract_text_first_page(pdf_path)
        return parse_station_metadata(text)
    except Exception as exc:
        if pdf_errors is not None:
            pdf_errors.append([pdf_path.name, str(exc)])
        return {}


def main():
    base_dir = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(
        description="Build a load-ready station table from BOM lists and metadata PDFs."
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
        "--output",
        default=str(base_dir / "data/output/station_table.csv"),
        help="Output CSV path.",
    )
    parser.add_argument(
        "--download-missing",
        action="store_true",
        help="Attempt to download missing metadata PDFs.",
    )
    parser.add_argument(
        "--download-limit",
        type=int,
        default=None,
        help="Limit number of missing PDFs to download.",
    )
    parser.add_argument(
        "--download-sleep",
        type=float,
        default=0.5,
        help="Seconds to sleep between downloads.",
    )
    parser.add_argument(
        "--write-download-errors",
        default=str(base_dir / "data/logs/download_errors.csv"),
        help="CSV path for failed PDF downloads.",
    )
    parser.add_argument(
        "--write-pdf-errors",
        default=str(base_dir / "data/logs/pdf_parse_errors.csv"),
        help="CSV path for PDF parse errors.",
    )
    args = parser.parse_args()

    metadata_dir = Path(args.metadata_dir)

    alpha_records, num_records, combined_lists = load_list_records(
        Path(args.alpha_list), Path(args.num_list)
    )
    list_sites = sorted(combined_lists.keys())

    existing_sites = collect_pdf_station_numbers(metadata_dir)
    missing_sites = [s for s in list_sites if s not in existing_sites]

    download_errors = []
    if args.download_missing and missing_sites:
        to_download = missing_sites
        if args.download_limit is not None:
            to_download = to_download[: args.download_limit]
        for site in to_download:
            ok, err = download_metadata_pdf(site, metadata_dir)
            if not ok:
                download_errors.append([site, err])
            time.sleep(args.download_sleep)
        if args.write_download_errors:
            with open(args.write_download_errors, "w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(["station_number", "error"])
                writer.writerows(download_errors)
        existing_sites = collect_pdf_station_numbers(metadata_dir)

    all_sites = sorted(existing_sites | set(list_sites))

    pdf_errors = []
    output_path = Path(args.output)
    fieldnames = [
        "bom_station_number",
        "station_name",
        "start_year",
        "end_year",
        "latitude",
        "longitude",
        "source",
        "state",
        "height",
        "bar_height",
        "wmo",
        "metadata_compiled",
        "bom_district_name",
        "identification",
        "network_classification",
        "station_purpose",
        "aws",
        "status",
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()

        for site in all_sites:
            pdf_name = station_number_to_pdf_name(site)
            pdf_path = metadata_dir / pdf_name
            metadata = {}
            if pdf_path.exists():
                metadata = read_metadata_record(pdf_path, pdf_errors)

            list_record = combined_lists.get(site, {})
            list_start_year = year_from_month_year(list_record.get("start"))
            list_end_year = year_from_month_year(list_record.get("end"))
            list_aws = normalize_aws(list_record.get("aws"))

            station_name = choose(list_record.get("name"), metadata.get("station_name"))
            latitude = choose(metadata.get("latitude"), list_record.get("lat"))
            longitude = choose(metadata.get("longitude"), list_record.get("lon"))
            start_year = choose(metadata.get("start_year"), list_start_year)
            end_year = choose(metadata.get("end_year"), list_end_year)
            aws = choose(normalize_aws(metadata.get("aws")), list_aws)

            row = {
                "bom_station_number": site,
                "station_name": station_name or "",
                "start_year": start_year or "",
                "end_year": end_year or "",
                "latitude": latitude or "",
                "longitude": longitude or "",
                "source": "BOM",
                "state": metadata.get("state") or "",
                "height": metadata.get("height") or "",
                "bar_height": metadata.get("bar_height") or "",
                "wmo": metadata.get("wmo") or "",
                "metadata_compiled": metadata.get("metadata_compiled") or "",
                "bom_district_name": metadata.get("bom_district_name") or "",
                "identification": metadata.get("identification") or "",
                "network_classification": metadata.get("network_classification") or "",
                "station_purpose": metadata.get("station_purpose") or "",
                "aws": aws or "",
                "status": metadata.get("status") or "",
            }
            writer.writerow(row)

    if args.write_pdf_errors:
        with open(args.write_pdf_errors, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["pdf_name", "error"])
            writer.writerows(pdf_errors)

    summary = {
        "list_station_count": len(list_sites),
        "metadata_station_count": len(existing_sites),
        "output_station_count": len(all_sites),
        "missing_metadata_count": len(missing_sites),
        "download_errors": len(download_errors),
        "pdf_parse_errors": len(pdf_errors),
        "output": str(output_path),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
