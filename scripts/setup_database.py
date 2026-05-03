#!/usr/bin/env python3
import argparse
import subprocess
from pathlib import Path

import psycopg2
from psycopg2 import sql

from config import get_db_params, load_config


def ensure_database(db_params):
    db_name = db_params["database"]
    admin_params = dict(db_params)
    admin_params["database"] = "postgres"

    with psycopg2.connect(**admin_params) as conn:
        conn.autocommit = True
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s;",
                (db_name,),
            )
            exists = cursor.fetchone() is not None
            if not exists:
                cursor.execute(sql.SQL("CREATE DATABASE {};").format(sql.Identifier(db_name)))


def run_psql(db_name, *args):
    cmd = ["psql", "-v", "ON_ERROR_STOP=1", "-d", db_name, *args]
    subprocess.run(cmd, check=True)


def load_schema(db_name, schema_path):
    run_psql(db_name, "-f", str(schema_path))


def load_station_table(db_name, csv_path):
    copy_sql = (
        "\\copy station "
        "(bom_station_number, station_name, start_year, end_year, latitude, longitude, "
        "source, state, height, bar_height, wmo, metadata_compiled, bom_district_name, "
        "identification, network_classification, station_purpose, aws, status) "
        f"FROM '{csv_path}' WITH (FORMAT csv, HEADER true)"
    )
    run_psql(db_name, "-c", copy_sql)


def load_equipment_tables(db_name, events_csv, elements_csv, tables_sql):
    run_psql(db_name, "-f", str(tables_sql))
    run_psql(
        db_name,
        "-c",
        "TRUNCATE station_equipment_event, station_equipment_element RESTART IDENTITY;",
    )

    copy_events = (
        "\\copy station_equipment_event_stage "
        "(bom_station_number, element, action, instrument_detail, system, event_date, source_pdf) "
        f"FROM '{events_csv}' WITH (FORMAT csv, HEADER true)"
    )
    run_psql(db_name, "-c", copy_events)

    insert_events = (
        "INSERT INTO station_equipment_event "
        "(bom_station_number, element, action, instrument_detail, system, event_date, source_pdf) "
        "SELECT bom_station_number::int, element, action, instrument_detail, system, "
        "CASE WHEN event_date = '' THEN NULL ELSE to_date(event_date, 'DD/MON/YYYY') END, "
        "source_pdf "
        "FROM station_equipment_event_stage;"
    )
    run_psql(db_name, "-c", insert_events)
    run_psql(db_name, "-c", "DROP TABLE station_equipment_event_stage;")

    copy_elements = (
        "\\copy station_equipment_element "
        "(bom_station_number, element, has_events, source_pdf) "
        f"FROM '{elements_csv}' WITH (FORMAT csv, HEADER true)"
    )
    run_psql(db_name, "-c", copy_elements)


def create_equipment_indexes(db_name):
    statements = [
        "CREATE INDEX IF NOT EXISTS station_equipment_event_station_idx "
        "ON station_equipment_event (bom_station_number);",
        "CREATE INDEX IF NOT EXISTS station_equipment_event_element_idx "
        "ON station_equipment_event (element);",
        "CREATE INDEX IF NOT EXISTS station_equipment_event_date_idx "
        "ON station_equipment_event (event_date);",
        "CREATE INDEX IF NOT EXISTS station_equipment_element_station_idx "
        "ON station_equipment_element (bom_station_number);",
        "CREATE INDEX IF NOT EXISTS station_equipment_element_element_idx "
        "ON station_equipment_element (element);",
        "CREATE OR REPLACE VIEW station_equipment_summary AS "
        "SELECT bom_station_number, COUNT(*) AS element_count, "
        "COUNT(*) FILTER (WHERE has_events = 'Y') AS elements_with_events "
        "FROM station_equipment_element GROUP BY bom_station_number;",
        "CREATE OR REPLACE VIEW station_equipment_event_summary AS "
        "SELECT bom_station_number, COUNT(*) AS event_count, "
        "MIN(event_date) AS first_event_date, MAX(event_date) AS last_event_date "
        "FROM station_equipment_event GROUP BY bom_station_number;",
    ]
    for stmt in statements:
        run_psql(db_name, "-c", stmt)


def main():
    parser = argparse.ArgumentParser(
        description="Create database (if needed) and load station/equipment tables."
    )
    parser.add_argument(
        "--database",
        default=None,
        help="Override database name from config.",
    )
    parser.add_argument(
        "--schema",
        default="sql/bom_clone_v3_schema.sql",
        help="Schema SQL file path.",
    )
    parser.add_argument(
        "--station-csv",
        default="data/output/station_table_known_state.csv",
        help="Station CSV to load.",
    )
    parser.add_argument(
        "--events-csv",
        default="data/output/station_equipment_events.csv",
        help="Equipment events CSV.",
    )
    parser.add_argument(
        "--elements-csv",
        default="data/output/station_equipment_elements.csv",
        help="Equipment elements CSV.",
    )
    parser.add_argument(
        "--equipment-sql",
        default="sql/station_equipment_tables.sql",
        help="Equipment table SQL file.",
    )
    parser.add_argument(
        "--skip-stations",
        action="store_true",
        help="Skip loading the station table.",
    )
    parser.add_argument(
        "--skip-equipment",
        action="store_true",
        help="Skip loading equipment tables.",
    )
    parser.add_argument(
        "--skip-indexes",
        action="store_true",
        help="Skip equipment indexes and views.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    config = load_config()
    db_params = get_db_params(config)
    if args.database:
        db_params["database"] = args.database

    db_name = db_params["database"]

    ensure_database(db_params)
    load_schema(db_name, repo_root / args.schema)

    if not args.skip_stations:
        load_station_table(db_name, repo_root / args.station_csv)

    if not args.skip_equipment:
        load_equipment_tables(
            db_name,
            repo_root / args.events_csv,
            repo_root / args.elements_csv,
            repo_root / args.equipment_sql,
        )
        if not args.skip_indexes:
            create_equipment_indexes(db_name)


if __name__ == "__main__":
    main()
