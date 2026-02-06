#!/usr/bin/env python3
"""Plot Darwin annual avg max temperature series for Post Office, Airport, and combined."""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import psycopg2

sys.path.append(str(Path(__file__).resolve().parent))
from config import get_db_params, load_config


REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "data" / "logs" / "analytics"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

STATIONS = {
    "DARWIN POST OFFICE": 14016,
    "DARWIN AIRPORT": 14015,
}


def fetch_station_series(conn, station_number: int):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXTRACT(YEAR FROM date)::int AS year,
                   AVG(max_temperature)::float AS avg_max_temp
            FROM daily_max_temperature
            WHERE bom_station_number = %s
            GROUP BY year
            ORDER BY year;
            """,
            (station_number,),
        )
        rows = cur.fetchall()
    years = [r[0] for r in rows]
    values = [r[1] for r in rows]
    return years, values


def plot_series(years, values, title, output_path, *, color="#1f77ff"):
    fig, ax = plt.subplots(figsize=(12, 4.8))
    ax.plot(
        years,
        values,
        color=color,
        linewidth=1.2,
        marker="s",
        markersize=3.5,
        markerfacecolor="white",
        markeredgewidth=0.9,
    )
    mean_value = sum(values) / len(values)
    ax.axhline(mean_value, color="#6c7a89", linewidth=1.0)

    ax.set_title(title)
    ax.set_xlabel("Year", color="#1f4da0")
    ax.set_ylabel("Mean maximum temperature (°C)", color="#1f4da0")
    ax.tick_params(axis="both", colors="#1f4da0")
    ax.grid(False)

    ax.plot([], [], color="#6c7a89", linewidth=1.0, label="mean")
    ax.plot([], [], color="#6c7a89", marker="x", linestyle="None", label="no data")
    ax.legend(loc="lower left", frameon=False)
    fig.tight_layout()
    fig.savefig(output_path, dpi=140)
    plt.close(fig)


def plot_combined(post_years, post_values, air_years, air_values, output_path):
    post_max = max(post_years) if post_years else None
    combined_years = []
    combined_values = []

    if post_years:
        for y, v in zip(post_years, post_values):
            if post_max is None or y <= post_max:
                combined_years.append(y)
                combined_values.append(v)

    if air_years:
        for y, v in zip(air_years, air_values):
            if post_max is None or y > post_max:
                combined_years.append(y)
                combined_values.append(v)

    fig, ax = plt.subplots(figsize=(12, 4.8))
    ax.plot(
        combined_years,
        combined_values,
        color="#1f77ff",
        linewidth=1.2,
        marker="s",
        markersize=3.5,
        markerfacecolor="white",
        markeredgewidth=0.9,
    )
    combined_mean = sum(combined_values) / len(combined_values)
    ax.axhline(combined_mean, color="#6c7a89", linewidth=1.0)
    if post_max:
        ax.axvline(post_max, color="#7f8c8d", linestyle="--", linewidth=0.8, alpha=0.8)
        ax.text(
            post_max,
            ax.get_ylim()[1],
            " Post Office end",
            va="top",
            ha="left",
            fontsize=8,
            color="#7f8c8d",
        )
    ax.set_title("Darwin Annual mean maximum temperature (Post Office → Airport)")
    ax.set_xlabel("Year", color="#1f4da0")
    ax.set_ylabel("Mean maximum temperature (°C)", color="#1f4da0")
    ax.tick_params(axis="both", colors="#1f4da0")
    ax.grid(False)

    ax.plot([], [], color="#6c7a89", linewidth=1.0, label="mean")
    ax.plot([], [], color="#6c7a89", marker="x", linestyle="None", label="no data")
    ax.legend(loc="lower left", frameon=False)
    fig.tight_layout()
    fig.savefig(output_path, dpi=140)
    plt.close(fig)


def main():
    config = load_config()
    db_params = get_db_params(config)

    with psycopg2.connect(**db_params) as conn:
        post_years, post_values = fetch_station_series(conn, STATIONS["DARWIN POST OFFICE"])
        air_years, air_values = fetch_station_series(conn, STATIONS["DARWIN AIRPORT"])

    if not post_years:
        raise SystemExit("No data found for Darwin Post Office.")
    if not air_years:
        raise SystemExit("No data found for Darwin Airport.")

    plot_series(
        post_years,
        post_values,
        "Darwin Post Office (014016) Annual mean maximum temperature",
        OUTPUT_DIR / "darwin_post_office_annual_avg_max_temperature.png",
    )
    plot_series(
        air_years,
        air_values,
        "Darwin Airport (014015) Annual mean maximum temperature",
        OUTPUT_DIR / "darwin_airport_annual_avg_max_temperature.png",
    )
    plot_combined(
        post_years,
        post_values,
        air_years,
        air_values,
        OUTPUT_DIR / "darwin_combined_annual_avg_max_temperature.png",
    )

    print("Wrote: darwin_post_office_annual_avg_max_temperature.png")
    print("Wrote: darwin_airport_annual_avg_max_temperature.png")
    print("Wrote: darwin_combined_annual_avg_max_temperature.png")


if __name__ == "__main__":
    main()
