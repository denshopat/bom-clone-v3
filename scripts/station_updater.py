import os
import re
import psycopg2
from psycopg2 import pool


class StationUpdater:
    def __init__(self, conn_params, log_file, download_dir, year):
        self.conn_params = conn_params
        self.log_file = log_file
        self.download_dir = download_dir
        self.year = year
        self.connection_pool = self._create_connection_pool()

    def _create_connection_pool(self):
        """Create a connection pool for the database."""
        return psycopg2.pool.SimpleConnectionPool(1, 10, **self.conn_params)

    def get_current_stations(self):
        """Fetch a list of active BOM station numbers for the specified year."""
        conn = self.connection_pool.getconn()
        cursor = conn.cursor()

        try:
            query = """
                SELECT bom_station_number
                FROM station
                WHERE start_year <= %s AND (end_year IS NULL OR end_year >= %s)
            """
            cursor.execute(query, (self.year, self.year))
            return [row[0] for row in cursor.fetchall()]

        finally:
            self.connection_pool.putconn(conn)
            cursor.close()

    def read_processed_urls(self):
        """Reads the log file and extracts station numbers from processed URLs."""
        if not os.path.exists(self.log_file):
            return set()

        with open(self.log_file, "r") as file:
            urls = file.read().splitlines()

        return set(self._extract_station_numbers_from_urls(urls))

    def _extract_station_numbers_from_urls(self, urls):
        """Extract station numbers from a list of URLs."""
        pattern = r"p_stn_num=(\d+)"
        return {re.search(pattern, url).group(1) for url in urls if re.search(pattern, url)}

    def check_downloaded_files__(self):
        """Checks the `newzips` directory for already downloaded files."""
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir)  # Create the directory if it doesn't exist
            return set()

        pattern = r"(\d{6})"  # Regex to extract station numbers from filenames
        downloaded_stations = set()

        for filename in os.listdir(self.download_dir):
            match = re.search(pattern, filename)
            if match:
                downloaded_stations.add(match.group(1))

        return downloaded_stations
    

    def check_downloaded_files(self):

        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir)  # Create the directory if it doesn't exist
            return set()

        pattern = r"_(\d{4,6})_"  # Regex to extract station numbers from filenames

        downloaded_stations = set()

        for filename in os.listdir(self.download_dir):
            #print(f"Checking file: {filename}")  # Debugging line
            match = re.search(pattern, filename)
            if match:
                downloaded_stations.add(match.group(1))

        print(f"Downloaded stations identified: {len(downloaded_stations)}")  # Debugging line
    
        return downloaded_stations


    

    def find_stations_to_update(self):
        """Determines which stations still need processing."""
        # Normalize station numbers to plain strings (no padding)
        db_stations = {str(station) for station in self.get_current_stations()}
        processed_stations = {str(station) for station in self.read_processed_urls()}
        downloaded_stations = {str(station) for station in self.check_downloaded_files()}

        # Debugging output
        print(f"Stations fetched from DB: {len(db_stations)}")
        print(f"Processed stations (log): {len(processed_stations)}")
        print(f"Downloaded stations (files): {len(downloaded_stations)}")

        # Subtract processed and downloaded from DB stations
        stations_to_update = db_stations - processed_stations - downloaded_stations

        # Debugging output
        print(f"Sample of stations to update: {list(stations_to_update)[:10]}")

        return stations_to_update


    
    def close(self):
        if self.connection_pool:
            # Close all connections in the pool
            self.connection_pool.closeall()
            print("Connection pool closed.")
    


# Example Usage
if __name__ == "__main__":
    conn_params = {
        'host': 'localhost',
        'database': 'bom_clone',
        'user': 'patrick',
        'password': 'your_password'
    }
    log_file = './data/logs/updater.log'
    download_dir = 'newzips'
    year = 2023

    updater = StationUpdater(conn_params, log_file, download_dir, year)

    try:
        stations_to_update = updater.find_stations_to_update()
        print("Stations to update:", stations_to_update)
    finally:
        updater.close()
