#!/usr/bin/env python3
"""Grid-weighted annual temperature series for Australia, 1910 to present.

Method (mirrors how BOM/CRU produce regional series):
  1. Per station-year, take the chosen daily metric (mean=(max+min)/2,
     or just max, or just min) and average over the year.
     Require at least 300 qualifying days in a year to count.
  2. Bin stations into 1 deg x 1 deg lat/lon cells. Cell value = simple
     mean of its station-year values (this avoids over-weighting clusters
     of stations in cities like Melbourne or Sydney).
  3. National value = cos(lat)-weighted mean across cells (cells nearer
     the equator cover more area than cells near 45 deg S).

Antarctic and sub-Antarctic stations (state='ANT') are excluded.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import psycopg2

sys.path.append(str(Path(__file__).resolve().parent))
from config import get_db_params, load_config


REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "data" / "logs" / "analytics"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

START_YEAR = 1910
MIN_DAYS_PER_YEAR = 300
GRID_DEG = 1.0
BASELINE_START = 1961
BASELINE_END = 1990


METRIC_QUERIES = {
    "mean": """
        SELECT
            s.bom_station_number,
            s.latitude,
            s.longitude,
            EXTRACT(YEAR FROM mx.date)::int AS year,
            AVG((mx.max_temperature + mn.min_temperature) / 2.0)::float AS mean_temp,
            COUNT(*) AS day_count
        FROM daily_max_temperature mx
        JOIN daily_min_temperature mn
            ON mn.bom_station_number = mx.bom_station_number
           AND mn.date = mx.date
        JOIN station s ON s.bom_station_number = mx.bom_station_number
        WHERE mx.date >= %s
          AND mx.max_temperature IS NOT NULL
          AND mn.min_temperature IS NOT NULL
          AND s.latitude IS NOT NULL
          AND s.longitude IS NOT NULL
          AND s.state <> 'ANT'
        GROUP BY s.bom_station_number, s.latitude, s.longitude, EXTRACT(YEAR FROM mx.date)
        HAVING COUNT(*) >= %s;
    """,
    "max": """
        SELECT
            s.bom_station_number,
            s.latitude,
            s.longitude,
            EXTRACT(YEAR FROM mx.date)::int AS year,
            AVG(mx.max_temperature)::float AS mean_temp,
            COUNT(*) AS day_count
        FROM daily_max_temperature mx
        JOIN station s ON s.bom_station_number = mx.bom_station_number
        WHERE mx.date >= %s
          AND mx.max_temperature IS NOT NULL
          AND s.latitude IS NOT NULL
          AND s.longitude IS NOT NULL
          AND s.state <> 'ANT'
        GROUP BY s.bom_station_number, s.latitude, s.longitude, EXTRACT(YEAR FROM mx.date)
        HAVING COUNT(*) >= %s;
    """,
    "min": """
        SELECT
            s.bom_station_number,
            s.latitude,
            s.longitude,
            EXTRACT(YEAR FROM mn.date)::int AS year,
            AVG(mn.min_temperature)::float AS mean_temp,
            COUNT(*) AS day_count
        FROM daily_min_temperature mn
        JOIN station s ON s.bom_station_number = mn.bom_station_number
        WHERE mn.date >= %s
          AND mn.min_temperature IS NOT NULL
          AND s.latitude IS NOT NULL
          AND s.longitude IS NOT NULL
          AND s.state <> 'ANT'
        GROUP BY s.bom_station_number, s.latitude, s.longitude, EXTRACT(YEAR FROM mn.date)
        HAVING COUNT(*) >= %s;
    """,
}

METRIC_LABELS = {
    "mean": ("mean", "Annual mean temperature"),
    "max": ("maximum", "Annual mean daily maximum temperature"),
    "min": ("minimum", "Annual mean daily minimum temperature"),
}


def fetch_station_years(conn, metric: str) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(METRIC_QUERIES[metric], (f"{START_YEAR}-01-01", MIN_DAYS_PER_YEAR))
        rows = cur.fetchall()
    return pd.DataFrame(
        rows,
        columns=["bom_station_number", "latitude", "longitude", "year", "mean_temp", "day_count"],
    )


def grid_weighted_annual(station_years: pd.DataFrame) -> pd.DataFrame:
    df = station_years.copy()
    df["lat_cell"] = np.floor(df["latitude"] / GRID_DEG).astype(int)
    df["lon_cell"] = np.floor(df["longitude"] / GRID_DEG).astype(int)

    cell_year = (
        df.groupby(["year", "lat_cell", "lon_cell"], as_index=False)
        .agg(cell_mean_temp=("mean_temp", "mean"), station_count=("bom_station_number", "nunique"))
    )

    cell_center_lat = (cell_year["lat_cell"] + 0.5) * GRID_DEG
    cell_year["weight"] = np.cos(np.radians(cell_center_lat))

    def weighted_avg(group: pd.DataFrame) -> pd.Series:
        w = group["weight"]
        v = group["cell_mean_temp"]
        return pd.Series(
            {
                "gridded_mean_temp": float((v * w).sum() / w.sum()),
                "cell_count": int(len(group)),
                "station_count": int(group["station_count"].sum()),
            }
        )

    annual = (
        cell_year.groupby("year", group_keys=False)
        .apply(weighted_avg, include_groups=False)
        .reset_index()
    )
    return annual


def add_anomaly_column(annual: pd.DataFrame) -> pd.DataFrame:
    baseline_mask = annual["year"].between(BASELINE_START, BASELINE_END)
    baseline_mean = float(annual.loc[baseline_mask, "gridded_mean_temp"].mean())
    annual = annual.copy()
    annual["anomaly_c"] = annual["gridded_mean_temp"] - baseline_mean
    annual.attrs["baseline_mean"] = baseline_mean
    return annual


def plot_absolute(annual: pd.DataFrame, output_path: Path, metric: str) -> None:
    short_label, full_label = METRIC_LABELS[metric]
    fig, ax = plt.subplots(figsize=(13, 5.2))
    ax.plot(
        annual["year"],
        annual["gridded_mean_temp"],
        color="#1f77ff",
        linewidth=1.2,
        marker="s",
        markersize=3.0,
        markerfacecolor="white",
        markeredgewidth=0.8,
        label="annual",
    )

    smooth = annual["gridded_mean_temp"].rolling(window=5, center=True, min_periods=3).mean()
    ax.plot(annual["year"], smooth, color="#d62728", linewidth=2.0, label="5-year smoothed")

    overall_mean = float(annual["gridded_mean_temp"].mean())
    ax.axhline(overall_mean, color="#6c7a89", linewidth=0.8, linestyle="--", label=f"long-term mean ({overall_mean:.2f} °C)")

    ax.set_title(
        f"Australia {full_label.lower()} (grid-weighted, {GRID_DEG:.0f}° cells, "
        f"{annual['year'].min()}–{annual['year'].max()})"
    )
    ax.set_xlabel("Year", color="#1f4da0")
    ax.set_ylabel(f"{full_label} (°C)", color="#1f4da0")
    ax.tick_params(axis="both", colors="#1f4da0")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="lower right", frameon=False)
    fig.tight_layout()
    fig.savefig(output_path, dpi=140)
    plt.close(fig)


def plot_anomaly(annual: pd.DataFrame, output_path: Path, metric: str) -> None:
    short_label, _ = METRIC_LABELS[metric]
    fig, ax = plt.subplots(figsize=(13, 5.2))
    colors = ["#d62728" if v >= 0 else "#1f77ff" for v in annual["anomaly_c"]]
    ax.bar(annual["year"], annual["anomaly_c"], color=colors, width=0.85, alpha=0.85)

    smooth = annual["anomaly_c"].rolling(window=5, center=True, min_periods=3).mean()
    ax.plot(annual["year"], smooth, color="black", linewidth=2.0, label="5-year smoothed")

    ax.axhline(0.0, color="#333333", linewidth=0.6)
    ax.set_title(
        f"Australia annual {short_label} temperature anomaly vs "
        f"{BASELINE_START}–{BASELINE_END} baseline (grid-weighted, {GRID_DEG:.0f}° cells)"
    )
    ax.set_xlabel("Year", color="#1f4da0")
    ax.set_ylabel("Anomaly (°C)", color="#1f4da0")
    ax.tick_params(axis="both", colors="#1f4da0")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="lower right", frameon=False)
    fig.tight_layout()
    fig.savefig(output_path, dpi=140)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--metric",
        choices=("mean", "max", "min"),
        default="mean",
        help="Daily metric to average per year (default: mean).",
    )
    args = parser.parse_args()

    config = load_config()
    db_params = get_db_params(config)

    print(f"Querying station-years from {START_YEAR} (metric={args.metric})…")
    with psycopg2.connect(**db_params) as conn:
        station_years = fetch_station_years(conn, args.metric)
    print(f"  {len(station_years):,} station-year rows; {station_years['bom_station_number'].nunique():,} stations.")

    annual = grid_weighted_annual(station_years)
    annual = add_anomaly_column(annual)

    suffix = "" if args.metric == "mean" else f"_{args.metric}"
    csv_path = OUTPUT_DIR / f"australia_grid_weighted_annual{suffix}_temp.csv"
    abs_path = OUTPUT_DIR / f"australia_grid_weighted_annual{suffix}_temp.png"
    anom_path = OUTPUT_DIR / f"australia_grid_weighted_annual{suffix}_temp_anomaly.png"

    annual.to_csv(csv_path, index=False)
    plot_absolute(annual, abs_path, args.metric)
    plot_anomaly(annual, anom_path, args.metric)

    baseline_mean = annual.attrs["baseline_mean"]
    latest = annual.iloc[-1]
    print(f"  baseline mean ({BASELINE_START}–{BASELINE_END}): {baseline_mean:.2f} °C")
    print(f"  latest year {int(latest['year'])}: {latest['gridded_mean_temp']:.2f} °C "
          f"(anomaly {latest['anomaly_c']:+.2f} °C)")
    print(f"Wrote: {abs_path.relative_to(REPO_ROOT)}")
    print(f"Wrote: {anom_path.relative_to(REPO_ROOT)}")
    print(f"Wrote: {csv_path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
