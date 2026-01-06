#!/usr/bin/env python3
import base64
import io
import time
from pathlib import Path

import matplotlib.pyplot as plt
import psycopg2
import warnings

from config import get_db_params, load_config


TABLES = {
    "daily_rainfall": "Rainfall",
    "daily_max_temperature": "Max Temperature",
    "daily_min_temperature": "Min Temperature",
}

warnings.filterwarnings(
    "ignore",
    message="Unable to import Axes3D",
)


def fetch_yearly_counts(conn, table):
    with conn.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT EXTRACT(YEAR FROM date)::int AS year,
                   COUNT(*) AS rows,
                   COUNT(DISTINCT bom_station_number) AS stations
            FROM {table}
            GROUP BY year
            ORDER BY year;
            """
        )
        return cursor.fetchall()


def plot_lines(series_map, title, ylabel):
    fig, ax = plt.subplots(figsize=(10, 4.5))
    for label, (years, values) in series_map.items():
        if years:
            ax.plot(years, values, label=label)
    ax.set_title(title)
    ax.set_xlabel("Year")
    ax.set_ylabel(ylabel)
    ax.grid(True, linestyle="--", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120)
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("ascii")


def main():
    repo_root = Path(__file__).resolve().parent.parent
    output_dir = repo_root / "data/logs/analytics"
    output_dir.mkdir(parents=True, exist_ok=True)

    config = load_config()
    db_params = get_db_params(config)

    summary = {
        "generated_at": time.time(),
        "db_tables": {},
    }

    try:
        with psycopg2.connect(**db_params) as conn:
            for table in TABLES:
                summary["db_tables"][table] = {}
                with conn.cursor() as cursor:
                    cursor.execute(f"SELECT COUNT(*) FROM {table};")
                    summary["db_tables"][table]["rows"] = cursor.fetchone()[0]

            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM station;")
                summary["stations_total"] = cursor.fetchone()[0]

            yearly_rows = {}
            yearly_stations = {}
            for table, label in TABLES.items():
                rows = fetch_yearly_counts(conn, table)
                years = [r[0] for r in rows]
                row_counts = [r[1] for r in rows]
                station_counts = [r[2] for r in rows]
                yearly_rows[label] = (years, row_counts)
                yearly_stations[label] = (years, station_counts)

    except Exception as exc:
        error_html = f"<p><strong>Database error:</strong> {exc}</p>"
        html = f"""<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <title>BOM Clone Analytics</title>
</head>
<body>
  <h1>BOM Clone Analytics</h1>
  {error_html}
</body>
</html>"""
        (output_dir / "analytics.html").write_text(html, encoding="utf-8")
        return

    rows_chart = plot_lines(yearly_rows, "Rows per Year", "Rows")
    stations_chart = plot_lines(yearly_stations, "Stations per Year", "Stations")

    table_rows = "".join(
        f"<tr><th>{table}</th><td>{summary['db_tables'][table]['rows']}</td></tr>"
        for table in TABLES
    )

    html = f"""<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <title>BOM Clone Analytics</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; }}
    table {{ border-collapse: collapse; margin-bottom: 20px; }}
    th, td {{ border: 1px solid #ddd; padding: 6px 10px; text-align: left; }}
    th {{ background: #f5f5f5; }}
    img {{ max-width: 100%; height: auto; }}
  </style>
</head>
<body>
  <h1>BOM Clone Analytics</h1>
  <p>Generated at {time.ctime(summary['generated_at'])}</p>
  <h2>Totals</h2>
  <table>
    <tr><th>Stations</th><td>{summary['stations_total']}</td></tr>
    {table_rows}
  </table>
  <h2>Rows per Year</h2>
  <img src="data:image/png;base64,{rows_chart}" alt="Rows per year" />
  <h2>Stations per Year</h2>
  <img src="data:image/png;base64,{stations_chart}" alt="Stations per year" />
</body>
</html>"""

    (output_dir / "analytics.html").write_text(html, encoding="utf-8")
    (output_dir / "analytics.json").write_text(json_dump(summary), encoding="utf-8")


def json_dump(data):
    import json

    return json.dumps(data, indent=2)


if __name__ == "__main__":
    main()
