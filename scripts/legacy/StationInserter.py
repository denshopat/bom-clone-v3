import os
import zipfile
import pandas as pd
from pandas.errors import EmptyDataError
from sqlalchemy import create_engine
from multiprocessing import Pool

from scr.config import get_paths, get_sqlalchemy_url, load_config

CONFIG = load_config()
DATABASE_CONFIG = CONFIG['Database']
PATHS = get_paths(CONFIG)
SQLALCHEMY_URL = get_sqlalchemy_url(DATABASE_CONFIG)


def init_db_connection():
    return create_engine(SQLALCHEMY_URL)


class BOMFileHandler:
    def __init__(self, base_dir, extract_dir):
        self.base_dir = base_dir
        self.extract_dir = extract_dir
        if self.base_dir:
            os.makedirs(self.base_dir, exist_ok=True)
        os.makedirs(extract_dir, exist_ok=True)

    def extract_all_zips(self):
        if not os.path.isdir(self.base_dir):
            print(f"No zip directory found at {self.base_dir}; skipping extraction.")
            return

        print("Evaluating zip files for extraction...")
        extracted_count = 0
        skipped_count = 0

        for filename in sorted(os.listdir(self.base_dir)):
            if not filename.endswith("_1800.zip"):
                continue

            zip_path = os.path.join(self.base_dir, filename)
            with zipfile.ZipFile(zip_path, 'r') as archive:
                data_members = []
                for member in archive.namelist():
                    normalized = os.path.normpath(member)
                    if normalized.endswith(os.sep):
                        continue
                    if ".." in normalized.split(os.sep):
                        continue
                    if normalized.endswith("_Data.csv"):
                        data_members.append(normalized)

                if not data_members:
                    print(f"Zip {filename} contains no *_Data.csv files; skipping.")
                    skipped_count += 1
                    continue

                needs_extraction = False
                for member in data_members:
                    target_path = os.path.join(self.extract_dir, member)
                    if not os.path.exists(target_path):
                        needs_extraction = True
                        break

                if not needs_extraction:
                    skipped_count += 1
                    continue

                archive.extractall(path=self.extract_dir, members=data_members)
                extracted_count += 1

        print(f"Extraction summary: {extracted_count} zip(s) unpacked, {skipped_count} already extracted.")

    def get_available_stations(self):
        available_stations = {}
        for root, _, files in os.walk(self.extract_dir):
            for filename in files:
                if not (filename.startswith("IDCJAC") and filename.endswith("_1800_Data.csv")):
                    continue
                parts = filename.split("_")
                if len(parts) < 3:
                    continue
                data_type = parts[0][-2:]
                station_id = parts[1].zfill(6)
                if station_id not in available_stations:
                    available_stations[station_id] = set()
                available_stations[station_id].add(data_type)
        return available_stations

def get_column_mapping(table_name):
    column_mappings = {
        'daily_rainfall': {
            'Product code': 'product_code',
            'Bureau of Meteorology station number': 'bom_station_number',
            'Year': 'year',
            'Month': 'month',
            'Day': 'day',
            'Rainfall amount (millimetres)': 'rainfall_amount',
            'Period over which rainfall was measured (days)': 'rainfall_period',
            'Quality': 'quality'
        },
        'daily_max_temperature': {
            'Product code': 'product_code',
            'Bureau of Meteorology station number': 'bom_station_number',
            'Year': 'year',
            'Month': 'month',
            'Day': 'day',
            'Maximum temperature (Degree C)': 'max_temperature',
            'Days of accumulation of maximum temperature': 'accumulation_days',
            'Quality': 'quality'
        },
        'daily_min_temperature': {
            'Product code': 'product_code',
            'Bureau of Meteorology station number': 'bom_station_number',
            'Year': 'year',
            'Month': 'month',
            'Day': 'day',
            'Minimum temperature (Degree C)': 'min_temperature',
            'Days of accumulation of minimum temperature': 'accumulation_days',
            'Quality': 'quality'
        }
    }
    return column_mappings.get(table_name, {})

def process_station_data(station_id, data_types, extract_dir):
    engine = init_db_connection()
    connection = engine.connect()
    categories = {
        'daily_rainfall': '09',
        'daily_max_temperature': '10',
        'daily_min_temperature': '11'
    }
    
    try:
        for table, data_type in categories.items():
            if data_type not in data_types:
                continue
            csv_filename = f"IDCJAC00{data_type}_{int(station_id)}_1800_Data.csv"
            csv_file_path = None
            for root, _, files in os.walk(extract_dir):
                if csv_filename in files:
                    csv_file_path = os.path.join(root, csv_filename)
                    break

            if not csv_file_path:
                print(f"[{station_id}] No CSV found for data type {data_type}; skipping {table}.")
                continue

            column_mapping = get_column_mapping(table)
            try:
                chunk_iterator = pd.read_csv(csv_file_path, chunksize=50000)
            except EmptyDataError:
                print(f"[{station_id}] Empty CSV at {csv_filename}; nothing loaded for {table}.")
                continue

            rows_written = 0
            chunk_index = 0
            for chunk in chunk_iterator:
                chunk_index += 1
                chunk.rename(columns=column_mapping, inplace=True)
                chunk['date'] = pd.to_datetime(chunk[['year', 'month', 'day']])
                chunk.drop(columns=['year', 'month', 'day'], inplace=True)
                chunk.to_sql(table, connection, if_exists='append', index=False, method='multi')
                rows_written += len(chunk)

            print(f"[{station_id}] Loaded {rows_written} row(s) into {table} from {chunk_index} chunk(s).")
    finally:
        connection.close()

def run_pipeline(base_dir, extract_dir):
    file_handler = BOMFileHandler(base_dir, extract_dir)
    file_handler.extract_all_zips()
    available_stations = file_handler.get_available_stations()
    if not available_stations:
        print("No extracted station data found to load.")
        return

    print(f"Preparing to load data for {len(available_stations)} station(s)...")

    with Pool() as pool:
        pool.starmap(process_station_data, [(station_id, data_types, extract_dir) for station_id, data_types in available_stations.items()])

    print("Data load pipeline completed.")

if __name__ == "__main__":
    base_dir = PATHS.get('zip_dir', 'newzips')
    extract_dir = PATHS.get('extract_dir', 'extracted')
    run_pipeline(base_dir, extract_dir)
