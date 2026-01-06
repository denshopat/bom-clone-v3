#!/usr/bin/env python3
import argparse
import tempfile
import urllib.request
from pathlib import Path


LISTS = {
    "alphaAUS_3.txt": "https://www.bom.gov.au/climate/data/lists_by_element/alphaAUS_3.txt",
    "numAUS_139.txt": "https://www.bom.gov.au/climate/data/lists_by_element/numAUS_139.txt",
}


def fetch_text(url, timeout=30):
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Gecko/20100101 Firefox/115.0",
        "Accept": "text/plain,text/html",
    }
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def is_valid_list(text):
    if "Bureau of Meteorology product" not in text:
        return False
    if "lists_by_element" in text and "access is blocked" in text.lower():
        return False
    if "Your access is blocked" in text:
        return False
    return "Site    Name" in text and "-" * 10 in text


def write_atomic(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=path.parent, encoding="utf-8") as tmp:
        tmp.write(text)
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
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="HTTP timeout seconds.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    failed = 0
    for filename, url in LISTS.items():
        try:
            text = fetch_text(url, timeout=args.timeout)
        except Exception as exc:
            failed += 1
            print(f"{filename}: download failed ({exc})")
            continue

        if not is_valid_list(text):
            failed += 1
            print(f"{filename}: invalid response (blocked or malformed)")
            continue

        write_atomic(output_dir / filename, text)
        print(f"{filename}: updated")

    if failed:
        raise SystemExit(f"{failed} list(s) failed")


if __name__ == "__main__":
    main()
