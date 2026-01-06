#!/usr/bin/env python3
import argparse
import csv
import tempfile
import time
import urllib.request
from pathlib import Path

from station_list_compare import parse_station_list


BASE_URL = "https://www.bom.gov.au/clim_data/cdio/metadata/pdf/siteinfo"


def station_number_to_pdf_name(station_number):
    return f"IDCJMD0040.{station_number:06d}.SiteInfo.pdf"


def fetch_pdf(url, timeout=30):
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Gecko/20100101 Firefox/115.0",
        "Accept": "application/pdf,text/html",
    }
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        content_type = resp.info().get("Content-Type", "")
        data = resp.read()
    return content_type, data


def is_pdf(content_type, data):
    if "application/pdf" in content_type.lower():
        return True
    return data.startswith(b"%PDF")


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
        filename = station_number_to_pdf_name(station_number)
        dest_path = metadata_dir / filename

        if dest_path.exists() and dest_path.stat().st_size > 0:
            skipped += 1
            continue
        if dest_path.exists() and dest_path.stat().st_size == 0:
            try:
                dest_path.unlink()
            except OSError:
                pass

        url = f"{BASE_URL}/{filename}"
        try:
            content_type, data = fetch_pdf(url)
            if not is_pdf(content_type, data):
                failures.append([station_number, url, "not_pdf"])
                continue
            write_atomic(dest_path, data)
            downloaded += 1
        except Exception as exc:
            failures.append([station_number, url, str(exc)])

        time.sleep(args.sleep)

    if failures:
        Path(args.log_file).parent.mkdir(parents=True, exist_ok=True)
        with open(args.log_file, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["station_number", "url", "error"])
            writer.writerows(failures)

    print(
        f"Metadata download summary: downloaded={downloaded}, skipped={skipped}, "
        f"failed={len(failures)}"
    )
    if failures:
        print(f"Failures logged to {args.log_file}")


if __name__ == "__main__":
    main()
