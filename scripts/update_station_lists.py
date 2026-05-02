#!/usr/bin/env python3
import argparse
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from bom_client import BomFetchError, fetch_station_list


LIST_NAMES = ("alphaAUS_3", "numAUS_139")


def write_atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", delete=False, dir=path.parent) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def main():
    parser = argparse.ArgumentParser(
        description="Download BOM station list files into data/lists."
    )
    parser.add_argument(
        "--output-dir",
        default=str(Path(__file__).resolve().parent.parent / "data/lists"),
        help="Directory to store list files.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    failed = 0
    for name in LIST_NAMES:
        filename = f"{name}.txt"
        try:
            body = fetch_station_list(name)
        except BomFetchError as exc:
            failed += 1
            print(f"{filename}: {exc}")
            continue

        write_atomic(output_dir / filename, body)
        print(f"{filename}: updated")

    if failed:
        raise SystemExit(f"{failed} list(s) failed")


if __name__ == "__main__":
    main()
