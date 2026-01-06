#!/usr/bin/env python3
import json
import time
from pathlib import Path

import psycopg2

from config import get_db_params, load_config


def count_lines(path):
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return max(sum(1 for _ in handle) - 1, 0)


def safe_count_files(path, pattern):
    if not path.exists():
        return 0
    return len(list(path.glob(pattern)))


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
                    cursor.execute(f"SELECT COUNT(*) FROM {table};")
                    counts[table] = cursor.fetchone()[0]
    except Exception as exc:
        counts["error"] = str(exc)
    return counts


def main():
    repo_root = Path(__file__).resolve().parent.parent
    config = load_config()
    db_params = get_db_params(config)

    logs_dir = repo_root / "data/logs"
    metadata_dir = repo_root / "data/metadata"
    zips_dir = Path(config["Paths"].get("zip_dir", "./data/zips"))

    summary = {
        "generated_at": time.time(),
        "metadata_pdfs": safe_count_files(metadata_dir, "*.pdf"),
        "zip_files": safe_count_files(zips_dir, "*.zip"),
        "metadata_download_failures": count_lines(logs_dir / "metadata_download_errors.csv"),
        "refresh_download_failures": count_lines(logs_dir / "refresh_download_errors.csv"),
        "extract_failures": count_lines(logs_dir / "extract_errors.csv"),
        "download_log_entries": count_lines(logs_dir / "updater.csv"),
    }
    summary.update({f"db_{k}": v for k, v in db_counts(db_params).items()})

    stamp = time.strftime("%Y%m%d_%H%M%S")
    json_path = logs_dir / f"summary_{stamp}.json"
    txt_path = logs_dir / f"summary_{stamp}.txt"
    logs_dir.mkdir(parents=True, exist_ok=True)

    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    lines = [f"Summary generated at {time.ctime(summary['generated_at'])}"]
    for key, value in summary.items():
        if key == "generated_at":
            continue
        lines.append(f"{key}: {value}")
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Wrote {json_path}")
    print(f"Wrote {txt_path}")


if __name__ == "__main__":
    main()
