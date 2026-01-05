#!/usr/bin/env python3
import argparse
import contextlib
import io
import json
import re
from pathlib import Path

from PyPDF2 import PdfReader
from PyPDF2.errors import PdfReadWarning

import warnings

warnings.filterwarnings("ignore", category=PdfReadWarning)


UNKNOWN_TOKENS = {
    "?",
    "N/A",
    "NO ID",
    "NOT AVAILABLE",
    "UNKNOWN",
}


def normalize_value(value):
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if cleaned.upper() in UNKNOWN_TOKENS:
        return None
    return cleaned


def normalize_int(value):
    value = normalize_value(value)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def normalize_float(value):
    value = normalize_value(value)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def extract_first(patterns, text, flags=re.IGNORECASE):
    for pattern in patterns:
        match = re.search(pattern, text, flags=flags)
        if match:
            return match.group(1).strip()
    return None


def extract_from_lines(patterns, lines):
    for line in lines:
        for pattern in patterns:
            match = re.search(pattern, line, flags=re.IGNORECASE)
            if match:
                return match.group(1).strip()
    return None


def extract_text(pdf_path):
    reader = PdfReader(str(pdf_path))
    chunks = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        chunks.append(page_text)
    return "\n".join(chunks)


def extract_text_first_page(pdf_path):
    reader = PdfReader(str(pdf_path))
    if not reader.pages:
        return ""
    return reader.pages[0].extract_text() or ""


def parse_station_metadata(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    full_text = " ".join(lines)

    record = {}

    record["metadata_compiled"] = normalize_value(
        extract_first(
            [
                r"Metadata compiled:\s*([0-9]{1,2}\s+[A-Za-z]{3}\s+\d{4})",
            ],
            full_text,
        )
    )

    record["station_name"] = normalize_value(
        extract_from_lines([r"^(.+?)\s+Station:$"], lines)
        or extract_first(
            [
                r"Location:\s*([A-Za-z0-9 /'()-]+?)\s*Station:",
                r"\b([A-Z][A-Z0-9 /'()-]+?)\s+Station:",
            ],
            full_text,
        )
    )

    record["location"] = normalize_value(
        extract_first(
            [r"\bLocation:\s*([A-Za-z0-9 /'()-]+?)\s*Station:"],
            full_text,
        )
        or extract_first(
            [r"\bLocation:\s*([A-Za-z0-9 /'()-]+)"],
            full_text,
        )
    )

    record["bom_station_number"] = normalize_int(
        extract_from_lines(
            [r"^(\d{3,6})\s+Bureau of Meteorology station number:$"], lines
        )
        or extract_first(
            [
                r"\b(\d{3,6})\s+Bureau of Meteorology station number:",
                r"\bBureau No\.\s*:\s*(\d{3,6})",
            ],
            full_text,
        )
    )

    record["bom_district_name"] = normalize_value(
        extract_from_lines(
            [r"^(.+?)\s+Bureau of Meteorology district name:$"], lines
        )
        or extract_first(
            [
                r"Bureau of Meteorology district name:\s*([A-Za-z0-9 /'()-]+)",
            ],
            full_text,
        )
    )

    record["state"] = normalize_value(
        extract_from_lines([r"^([A-Z]{2,3})\s+State:$"], lines)
        or extract_first(
            [
                r"\b([A-Z]{2,3})\s*State:",
                r"State:\s*([A-Z]{2,3})",
            ],
            full_text,
        )
    )

    record["wmo"] = normalize_int(
        extract_from_lines(
            [r"^([0-9?]+)\s+World Meteorological Organization number:$"], lines
        )
        or extract_first([r"\bWMO No\.\s*:\s*([0-9?]+)"], full_text)
    )

    record["aviation_id"] = normalize_value(
        extract_first([r"Aviation ID:\s*([A-Za-z0-9-]+)"], full_text)
    )

    record["identification"] = normalize_value(
        extract_from_lines([r"^(.+?)\s+Identification:$"], lines)
        or extract_first([r"Identification:\s*([A-Za-z0-9 /'()-]+)"], full_text)
    )

    record["network_classification"] = normalize_value(
        extract_from_lines([r"^(.+?)\s+Network Classification:$"], lines)
        or extract_first(
            [r"Network Classification:\s*([A-Za-z0-9 /'()-]+)"], full_text
        )
    )

    record["station_purpose"] = normalize_value(
        extract_from_lines([r"^(.+?)\s+Station purpose:$"], lines)
        or extract_first([r"Station purpose:\s*([A-Za-z0-9 /'()-]+)"], full_text)
    )

    record["aws"] = normalize_value(
        extract_from_lines([r"^(.+?)\s+Automatic Weather Station:$"], lines)
        or extract_first(
            [r"Automatic Weather Station:\s*([A-Za-z0-9 /'()-]+)"], full_text
        )
    )

    record["status"] = normalize_value(
        extract_from_lines([r"^([A-Za-z]+)\s+Status:$"], lines)
        or extract_first(
            [
                r"\bCurrent Status:\s*([A-Za-z]+)",
                r"\b([A-Za-z]+)\s+Status:",
            ],
            full_text,
        )
    )

    record["latitude"] = normalize_float(
        extract_first(
            [
                r"(-?\d{1,2}\.\d+)\s*Decimal Latitude",
                r"Latitude:\s*(-?\d{1,2}\.\d+)",
            ],
            full_text,
        )
    )

    record["longitude"] = normalize_float(
        extract_first(
            [
                r"(-?\d{1,3}\.\d+)\s*Decimal Longitude",
                r"Longitude:\s*(-?\d{1,3}\.\d+)",
            ],
            full_text,
        )
    )

    record["lat_dms"] = normalize_value(
        extract_first(
            [
                r"(\d{1,2}[^0-9]{0,3}\d{1,2}[^0-9]{0,3}\d{1,2}[^0-9]{0,3}[NS])\s+Hour",
                r"\b(\d{1,2}[^0-9]{0,3}\d{1,2}[^0-9]{0,3}\d{1,2}[^0-9]{0,3}[NS])\b",
            ],
            full_text,
        )
    )

    record["lon_dms"] = normalize_value(
        extract_first(
            [
                r"(\d{1,3}[^0-9]{0,3}\d{1,2}[^0-9]{0,3}\d{1,2}[^0-9]{0,3}[EW])\s+Hour",
                r"\b(\d{1,3}[^0-9]{0,3}\d{1,2}[^0-9]{0,3}\d{1,2}[^0-9]{0,3}[EW])\b",
            ],
            full_text,
        )
    )

    record["height"] = normalize_float(
        extract_first(
            [
                r"Elevation:\s*([0-9]+(?:\.\d+)?)",
                r"Station Height\s*([0-9]+(?:\.\d+)?)\s*m",
            ],
            full_text,
        )
    )

    record["bar_height"] = normalize_float(
        extract_first(
            [
                r"Barometer Elev:\s*([0-9]+(?:\.\d+)?)\s*m",
                r"Barometer Height\s*([0-9]+(?:\.\d+)?)\s*m",
            ],
            full_text,
        )
    )

    record["start_year"] = normalize_int(
        extract_from_lines([r"^(\d{4})\s+Year opened:$"], lines)
        or extract_first(
            [
                r"Year opened:\s*(\d{4})",
                r"Opened:\s*\d{1,2}\s+[A-Za-z]{3}\s+(\d{4})",
            ],
            full_text,
        )
    )

    record["end_year"] = normalize_int(
        extract_first(
            [r"Closed:\s*\d{1,2}\s+[A-Za-z]{3}\s+(\d{4})"],
            full_text,
        )
    )

    record["opened_date"] = normalize_value(
        extract_first([r"Opened:\s*(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})"], full_text)
    )

    record["closed_date"] = normalize_value(
        extract_first([r"Closed:\s*(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})"], full_text)
    )

    record["geo_positioning_method"] = normalize_value(
        extract_first(
            [r"Method of station geographic positioning\s*(.+)$"],
            " ".join(lines),
        )
    )

    record["station_summary_text"] = normalize_value(
        extract_first(
            [
                r"Status:\s*[A-Za-z]+\s*:\s*(.+?)\s+Historical metadata",
                r"Status:\s*[A-Za-z]+\s*:\s*(.+?)\s+Observation summary",
                r"(No summary[^.]*\.)",
            ],
            full_text,
            flags=re.IGNORECASE | re.DOTALL,
        )
    )
    if record["station_summary_text"]:
        record["station_summary_text"] = " ".join(
            record["station_summary_text"].split()
        )

    return record


def iter_pdfs(metadata_dir):
    return sorted(metadata_dir.glob("*.pdf"))


def main():
    parser = argparse.ArgumentParser(
        description="Scrape BoM station metadata PDFs without storing results."
    )
    default_metadata_dir = Path(__file__).resolve().parent.parent / "data/metadata"
    parser.add_argument(
        "--metadata-dir",
        default=str(default_metadata_dir),
        help="Directory containing station metadata PDFs.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional limit on number of PDFs to parse.",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Only print field coverage summary.",
    )
    parser.add_argument(
        "--show-warnings",
        action="store_true",
        help="Show PDF parse warnings on stderr.",
    )
    args = parser.parse_args()

    metadata_dir = Path(args.metadata_dir)
    if not metadata_dir.exists():
        raise SystemExit(f"Metadata dir not found: {metadata_dir}")

    pdf_paths = iter_pdfs(metadata_dir)
    if args.limit is not None:
        pdf_paths = pdf_paths[: args.limit]

    coverage = {}
    total = 0

    for pdf_path in pdf_paths:
        if args.show_warnings:
            text = extract_text(pdf_path)
        else:
            with contextlib.redirect_stderr(io.StringIO()):
                text = extract_text(pdf_path)
        record = parse_station_metadata(text)
        record["source_pdf"] = pdf_path.name
        record["bom_url"] = (
            "https://www.bom.gov.au/clim_data/cdio/metadata/pdf/siteinfo/"
            f"{pdf_path.name}"
        )

        total += 1
        for key, value in record.items():
            if key == "source_pdf":
                continue
            coverage.setdefault(key, 0)
            if value is not None:
                coverage[key] += 1

        if not args.summary_only:
            print(json.dumps(record, ensure_ascii=True))

    print("\nCoverage summary:")
    for key in sorted(coverage):
        print(f"{key}: {coverage[key]}/{total}")


if __name__ == "__main__":
    main()
