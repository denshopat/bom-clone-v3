import os
import zipfile
import pandas as pd
from sqlalchemy import create_engine, text

from scr.config import get_paths, get_sqlalchemy_url, load_config

CONFIG = load_config()
DATABASE_CONFIG = CONFIG['Database']
PATHS = get_paths(CONFIG)
SQLALCHEMY_URL = get_sqlalchemy_url(DATABASE_CONFIG)


class BOMDatabaseManager:
    def __init__(self, engine=None):
        self.engine = engine or create_engine(SQLALCHEMY_URL)

    def replace_table(self, df, table_name, station_id):
        with self.engine.begin() as connection:
            connection.execute(text(f"DELETE FROM {table_name} WHERE bom_station_number = :station_id"), {'station_id': station_id})
        df.to_sql(table_name, self.engine, if_exists='append', index=False)
        print(f"Replaced table: {table_name}")

class BOMFileHandler:
    def __init__(self, base_dir):
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)

    def get_available_stations(self):
        available_stations = {}
        for filename in os.listdir(self.base_dir):
            if filename.startswith("IDCJAC") and filename.endswith("_1800.zip"):
                parts = filename.split("_")
                if len(parts) < 3:
                    continue
                data_type = parts[0][-2:]
                station_id = parts[1].zfill(6)
                if station_id not in available_stations:
                    available_stations[station_id] = set()
                available_stations[station_id].add(data_type)
        return available_stations

    def extract_csv_from_zip(self, station_id, data_type):
        zip_pattern = f"IDCJAC00{data_type}_{int(station_id)}_1800.zip"
        zip_file_path = os.path.join(self.base_dir, zip_pattern)
        target_file = f"IDCJAC00{data_type}_{int(station_id)}_1800_Data.csv"
        
        if not os.path.exists(zip_file_path):
            return None
        
        with zipfile.ZipFile(zip_file_path, 'r') as z:
            if target_file in z.namelist():
                with z.open(target_file) as file:
                    df = pd.read_csv(file)
                    return df
            return None

class BOMDataProcessor:
    def __init__(self, db_manager, file_handler, ignore_list_file='missing_stations_report.csv'):
        self.db_manager = db_manager
        self.file_handler = file_handler
        self.available_stations = file_handler.get_available_stations()
        self.ignore_stations, self.ignore_types = self.load_ignore_list(ignore_list_file)

    def load_ignore_list(self, file_path):
        if os.path.exists(file_path):
            df = pd.read_csv(file_path, header=None, names=['station_id', 'data_type', 'station_name'])
            ignore_stations = set(df['station_id'].astype(str))
            ignore_types = df.groupby('station_id')['data_type'].apply(set).to_dict()
            return ignore_stations, ignore_types
        return set(), {}

    def process_stations(self):
        for station_id, data_types in self.available_stations.items():
            if station_id in self.ignore_stations:
                print(f"Skipping station {station_id} for certain data types as per ignore list.")
            self.process_station_data(station_id, data_types)

    def process_station_data(self, station_id, data_types):
        categories = {
            'daily_rainfall': '09',
            'daily_max_temperature': '10',
            'daily_min_temperature': '11'
        }
        
        for table, data_type in categories.items():
            if data_type not in data_types:
                print(f"Skipping {table} for station {station_id} as no corresponding zip file exists.")
                continue
            if station_id in self.ignore_types and table in self.ignore_types[station_id]:
                print(f"Skipping {table} for station {station_id} as per ignore list.")
                continue
            df = self.file_handler.extract_csv_from_zip(station_id, data_type)
            if df is not None and not df.empty:
                column_mapping = self.get_column_mapping(table)
                df.rename(columns=column_mapping, inplace=True)
                self.db_manager.replace_table(df, table, station_id)
            else:
                print(f"No data for {station_id} in {table}")

    def get_column_mapping(self, table_name):
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

class BOMPipeline:
    def __init__(self, base_dir=None):
        base_dir = base_dir or PATHS.get('zip_dir', 'newzips')
        self.db_manager = BOMDatabaseManager()
        self.file_handler = BOMFileHandler(base_dir)
        self.processor = BOMDataProcessor(self.db_manager, self.file_handler)

    def run(self):
        self.processor.process_stations()

if __name__ == "__main__":
    pipeline = BOMPipeline()
    pipeline.run()
