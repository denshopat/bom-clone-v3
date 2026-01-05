#!/usr/bin/env python3
import argparse
import contextlib
import csv
import io
import re
from pathlib import Path

from PyPDF2 import PdfReader


ACTION_RE = re.compile(r"^(INSTALL|REMOVE|REPLACE|SHARE|UNSHARE)\s+(.+)$")
DATE_RE = re.compile(r"(\d{2}/[A-Z]{3}/\d{4})$")

SYSTEMS = [
    "Surface Observations",
    "Rainfall Intensity",
    "Weather Watch {RADAR}",
    "Weather Watch (RADAR)",
    "Weather Watch Radar",
    "Upper Air",
    "Flood Warning",
    "Infrastructure",
    "Radiation",
]

STOP_PREFIXES = (
    "Historical metadata for this site",
    "The following table summarises",
    "The following notes have been compiled",
    "Station Detail Changes",
    "Notes on these metadata",
)


def station_number_from_filename(filename):
    parts = filename.split(".")
    if len(parts) < 3:
        return None
    try:
        return int(parts[1])
    except ValueError:
        return None


def normalize_header(line):
    return line.replace("(No Electronic History)", "").strip()


def extract_equipment_lines(pdf_path):
    reader = PdfReader(str(pdf_path))
    collecting = False
    lines = []

    for page in reader.pages:
        text = page.extract_text() or ""
        if not text:
            continue
        if not collecting:
            start = text.find("Equipment Install/Remove")
            if start == -1:
                continue
            collecting = True
            text = text[start:]

        page_lines = [line.strip() for line in text.splitlines() if line.strip()]
        lines.extend(page_lines)

        if any(line.startswith(STOP_PREFIXES) for line in page_lines):
            break

    return lines


def split_action_line(line):
    match = ACTION_RE.match(line)
    if not match:
        return None
    action = match.group(1)
    remainder = match.group(2)

    date_match = DATE_RE.search(remainder)
    event_date = None
    if date_match:
        event_date = date_match.group(1)
        remainder = remainder[: date_match.start()].strip()

    system = None
    for sys_name in sorted(SYSTEMS, key=len, reverse=True):
        if remainder.endswith(sys_name):
            system = sys_name
            remainder = remainder[: -len(sys_name)].strip()
            break

    return action, remainder, system, event_date


def parse_equipment(lines):
    if not lines:
        return [], []

    events = []
    elements = {}
    current_element = None

    idx = 0
    while idx < len(lines):
        line = lines[idx]
        if line.startswith(STOP_PREFIXES):
            break

        match = ACTION_RE.match(line)
        if match:
            if not DATE_RE.search(line) and idx + 1 < len(lines):
                line = f"{line} {lines[idx + 1]}"
                idx += 1

            parsed = split_action_line(line)
            if parsed and current_element:
                action, detail, system, event_date = parsed
                events.append(
                    {
                        "element": current_element,
                        "action": action,
                        "instrument_detail": detail,
                        "system": system or "",
                        "event_date": event_date or "",
                    }
                )
            idx += 1
            continue

        header = normalize_header(line)
        if header and not DATE_RE.search(header):
            current_element = header
            if current_element not in elements:
                elements[current_element] = {"has_events": False}
        idx += 1

    for event in events:
        if event["element"] in elements:
            elements[event["element"]]["has_events"] = True

    element_rows = [
        {"element": name, "has_events": "Y" if info["has_events"] else "N"}
        for name, info in sorted(elements.items())
    ]

    return events, element_rows


def main():
    parser = argparse.ArgumentParser(
        description="Extract station equipment history from BOM metadata PDFs."
    )
    parser.add_argument(
        "--metadata-dir",
        default=str(Path(__file__).resolve().parent.parent / "data/metadata"),
        help="Directory containing station metadata PDFs.",
    )
    parser.add_argument(
        "--events-out",
        default=str(Path(__file__).resolve().parent.parent / "data/output/station_equipment_events.csv"),
        help="CSV output for equipment events.",
    )
    parser.add_argument(
        "--elements-out",
        default=str(Path(__file__).resolve().parent.parent / "data/output/station_equipment_elements.csv"),
        help="CSV output for equipment elements.",
    )
    parser.add_argument(
        "--errors-out",
        default=str(Path(__file__).resolve().parent.parent / "data/logs/equipment_parse_errors.csv"),
        help="CSV output for parse errors.",
    )
    args = parser.parse_args()

    metadata_dir = Path(args.metadata_dir)

    event_rows = []
    element_rows = []
    error_rows = []

    for pdf_path in sorted(metadata_dir.glob("IDCJMD0040.*.SiteInfo.pdf")):
        station_number = station_number_from_filename(pdf_path.name)
        if station_number is None:
            continue
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                lines = extract_equipment_lines(pdf_path)
            events, elements = parse_equipment(lines)
            for event in events:
                event_rows.append(
                    {
                        "bom_station_number": station_number,
                        "element": event["element"],
                        "action": event["action"],
                        "instrument_detail": event["instrument_detail"],
                        "system": event["system"],
                        "event_date": event["event_date"],
                        "source_pdf": pdf_path.name,
                    }
                )
            for element in elements:
                element_rows.append(
                    {
                        "bom_station_number": station_number,
                        "element": element["element"],
                        "has_events": element["has_events"],
                        "source_pdf": pdf_path.name,
                    }
                )
        except Exception as exc:
            error_rows.append([station_number, pdf_path.name, str(exc)])

    with open(args.events_out, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "bom_station_number",
                "element",
                "action",
                "instrument_detail",
                "system",
                "event_date",
                "source_pdf",
            ],
        )
        writer.writeheader()
        writer.writerows(event_rows)

    with open(args.elements_out, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "bom_station_number",
                "element",
                "has_events",
                "source_pdf",
            ],
        )
        writer.writeheader()
        writer.writerows(element_rows)

    if args.errors_out:
        with open(args.errors_out, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["bom_station_number", "source_pdf", "error"])
            writer.writerows(error_rows)

    print(f"events: {len(event_rows)}")
    print(f"elements: {len(element_rows)}")
    print(f"errors: {len(error_rows)}")


if __name__ == "__main__":
    main()
