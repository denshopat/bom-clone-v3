#!/usr/bin/env python3
import csv
import json
import time
from pathlib import Path

import psycopg2
from psycopg2 import sql

from config import get_db_params, load_config


def count_lines(path):
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for _ in handle) - 1


def safe_count_files(path, pattern):
    if not path.exists():
        return 0
    return len(list(path.glob(pattern)))


def read_last_step(state_file):
    if not state_file.exists():
        return "none"
    data = state_file.read_text(encoding="utf-8")
    for line in data.splitlines():
        if line.startswith("LAST_STEP="):
            return line.split("=", 1)[1].strip().strip('"')
    return "unknown"


def db_counts(db_params):
    counts = {}
    try:
        with psycopg2.connect(**db_params) as conn:
            with conn.cursor() as cursor:
                for table in [
                    "station",
                    "station_equipment_event",
                    "station_equipment_element",
                    "daily_rainfall",
                    "daily_max_temperature",
                    "daily_min_temperature",
                ]:
                    cursor.execute(sql.SQL("SELECT COUNT(*) FROM {};").format(sql.Identifier(table)))
                    counts[table] = cursor.fetchone()[0]
    except Exception as exc:
        counts["error"] = str(exc)
    return counts


def write_status(repo_root, data):
    status_json = repo_root / "data/logs/status.json"
    status_html = repo_root / "data/logs/status.html"
    status_json.parent.mkdir(parents=True, exist_ok=True)

    status_json.write_text(json.dumps(data, indent=2), encoding="utf-8")

    rows = "".join(
        f"<tr><th>{key}</th><td>{value}</td></tr>" for key, value in data.items()
    )
    html = f"""<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <meta http-equiv=\"refresh\" content=\"30\" />
  <title>BOM Clone Status</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; }}
    table {{ border-collapse: collapse; }}
    th, td {{ border: 1px solid #ddd; padding: 6px 10px; text-align: left; }}
    th {{ background: #f5f5f5; }}
    .meta {{ color: #666; margin-top: 8px; }}
  </style>
</head>
<body>
  <h1>BOM Clone Status</h1>
  <table>
    {rows}
  </table>
  <div class=\"meta\">Auto-refresh every 30s. Generated at {time.ctime(data['generated_at'])}</div>
</body>
</html>"""
    status_html.write_text(html, encoding="utf-8")


def main():
    repo_root = Path(__file__).resolve().parent.parent
    config = load_config()
    db_params = get_db_params(config)

    logs_dir = repo_root / "data/logs"
    metadata_dir = repo_root / "data/metadata"
    zips_dir = Path(config["Paths"].get("zip_dir", "./data/zips"))

    data = {
        "generated_at": time.time(),
        "last_step": read_last_step(logs_dir / "run_state.env"),
        "metadata_pdfs": safe_count_files(metadata_dir, "*.pdf"),
        "zip_files": safe_count_files(zips_dir, "*.zip"),
        "metadata_download_failures": count_lines(logs_dir / "metadata_download_errors.csv"),
        "refresh_download_failures": count_lines(logs_dir / "refresh_download_errors.csv"),
        "extract_failures": count_lines(logs_dir / "extract_errors.csv"),
        "download_log_entries": count_lines(logs_dir / "updater.csv"),
    }

    data.update({f"db_{k}": v for k, v in db_counts(db_params).items()})

    write_status(repo_root, data)


if __name__ == "__main__":
    main()
