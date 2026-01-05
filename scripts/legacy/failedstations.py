import os
import re
import pandas as pd
import psycopg2

from scr.config import get_db_params, get_paths, load_config

CONFIG = load_config()
DB_PARAMS = get_db_params(CONFIG)
PATHS = get_paths(CONFIG)
LOG_FILE = PATHS.get('download_log', PATHS.get('log_file', 'updater.log'))
OUTPUT_CSV = "missing_stations_report.csv"  # Output file


def extract_missing_stations(log_file):
    """Extracts station numbers and observation types from the log file."""
    missing_stations = []

    # Regex pattern to extract station number and observation code
    pattern = re.compile(r"p_nccObsCode=(\d+)&p_display_type=dailyDataFile&p_stn_num=(\d+)")

    if not os.path.exists(log_file):
        print(f"Log file not found at {log_file}. Nothing to extract.")
        return pd.DataFrame(columns=["Station Number", "Data Type"])

    with open(log_file, 'r') as file:
        for line in file:
            if "No data available" in line:
                match = pattern.search(line)
                if match:
                    obs_code, station_number = match.groups()
                    data_type = {
                        "136": "Rainfall",
                        "122": "Max Temperature",
                        "123": "Min Temperature"
                    }.get(obs_code, "Unknown")

                    print(f"📌 Found missing: Station {station_number} ({data_type})")
                    missing_stations.append({"Station Number": station_number, "Data Type": data_type})

    df = pd.DataFrame(missing_stations).drop_duplicates()
    print(f"🛠 Extracted {len(df)} missing stations.")  # Print how many were found
    return df


def get_station_names_from_db(station_numbers, db_params):
    """Retrieves station names from PostgreSQL for given station numbers."""
    if not station_numbers:
        return {}

    connection = psycopg2.connect(**db_params)
    cursor = connection.cursor()

    valid_numbers = []
    for num in station_numbers:
        try:
            valid_numbers.append(int(num))
        except ValueError:
            continue

    if not valid_numbers:
        cursor.close()
        connection.close()
        return {}

    query = """
        SELECT bom_station_number, station_name
        FROM station
        WHERE bom_station_number = ANY(%s);
    """

    cursor.execute(query, (valid_numbers,))
    results = cursor.fetchall()

    # Close connection
    cursor.close()
    connection.close()

    # Convert results to a dictionary {station_number: station_name}
    return {str(row[0]): row[1] for row in results}


def generate_missing_stations_report(log_file, db_params, output_csv):
    """Extracts missing stations, retrieves names from DB, and saves to CSV."""
    print("🔍 Extracting missing stations from log file...")
    missing_stations_df = extract_missing_stations(log_file)

    if missing_stations_df.empty:
        print("✅ No missing stations found in log file.")
        return

    print("🔍 Fetching station names from database...")
    station_numbers = missing_stations_df["Station Number"].tolist()
    station_names = get_station_names_from_db(station_numbers, db_params)

    print("📝 Adding station names...")
    missing_stations_df["Station Name"] = missing_stations_df["Station Number"].map(station_names)

    print("💾 Saving to CSV...")
    missing_stations_df.to_csv(output_csv, index=False)
    
    print(f"✅ Missing stations report saved as {output_csv}")


if __name__ == "__main__":
    generate_missing_stations_report(LOG_FILE, DB_PARAMS, OUTPUT_CSV)
