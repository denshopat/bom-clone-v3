from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
import urllib.request
import time
import re
import os
import requests
import psycopg2
import pandas as pd
from psycopg2 import pool
from concurrent.futures import ThreadPoolExecutor

from scr.config import get_db_params, get_paths, load_config


def ensure_parent_directory(path: str) -> None:
    """Ensure directories for a file path exist."""
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)



class StationUpdater:
    def __init__(self, conn_params, log_file, download_dir, year):
        self.conn_params = conn_params
        self.log_file = log_file
        self.download_dir = download_dir
        self.year = year
        self.connection_pool = self._create_connection_pool()
        os.makedirs(self.download_dir, exist_ok=True)
        ensure_parent_directory(self.log_file)

    def _create_connection_pool(self):
        return psycopg2.pool.SimpleConnectionPool(1, 10, **self.conn_params)

    
    def fetch_data(self, url):
        HEADERS = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        return response.text
    
    def process_data(self, url, data_type):
        """Fetches and processes station data from BOM."""
        data = self.fetch_data(url)

        if data_type == "rainfall":
            df = self.parse_rainfall_data(data)
        elif data_type == "temperature":
            df = self.parse_temperature_data(data)
        else:
            raise ValueError(f"Invalid data type: {data_type}")

        return self.check_stations_in_database(df)

    def parse_rainfall_data(self, data):
        """Parses rainfall station data."""
        pattern = re.compile(
            r"(\d{1,6})\s+"  # Site
            r"(.{1,40})\s+"  # Name
            r"(-?\d+\.\d{4})\s+"  # Latitude
            r"(-?\d+\.\d{4})\s+"  # Longitude
            r"([A-Za-z]{3} \d{4})\s+"  # Start (Month Year)
            r"([A-Za-z]{3} \d{4})\s+"  # End (Month Year)
            r"([\d.]+)\s+"  # Years
            r"([\d.]+)\s+"  # % Observations
            r"(Y|N)?"  # AWS (Y/N)
        )
        matches = pattern.findall(data)
        return pd.DataFrame(matches, columns=["Site", "Name", "Latitude", "Longitude", "Start", "End", "Years", "% Observations", "AWS"])

    def parse_temperature_data(self, data):
        """Parses temperature station data."""
        pattern = re.compile(
            r"(\d{1,6})\s+"  
            r"(.{1,40})\s+"  
            r"(-?\d+\.\d{4})\s+"  
            r"(-?\d+\.\d{4})\s+"  
            r"([A-Za-z]{3} \d{4})\s+"  
            r"([A-Za-z]{3} \d{4})\s+"  
            r"([\d.]+)\s+"  
            r"([\d.]+)\s+"  
            r"([\d.]+)\s+"  
            r"(Y|N)?"  
        )
        matches = pattern.findall(data)
        return pd.DataFrame(matches, columns=["Site", "Name", "Latitude", "Longitude", "Start", "End", "Years", "% Observations", "Obs", "AWS"])

    
    def check_stations_in_database(self, df):
        """Checks if stations exist in the database and adds a column to the DataFrame."""
        db_stations = self.get_all_stations()
        df["Exists in DB"] = df["Site"].astype(str).isin(db_stations)
        return df

    def get_all_stations(self):
        """Retrieves all station numbers from the database."""
        conn = self.connection_pool.getconn()
        cursor = conn.cursor()
        try:
            query = "SELECT bom_station_number FROM station"
            cursor.execute(query)
            return {str(row[0]) for row in cursor.fetchall()}
        finally:
            cursor.close()
            self.connection_pool.putconn(conn)

    
    
    
    
    def generate_bom_urls(self, rainfall_df, temperature_df):
        """Generates BOM URLs for rainfall and temperature data."""
        base_url = "http://www.bom.gov.au/jsp/ncc/cdio/weatherData/av"
        
        def build_url(station_number, obs_code):
            return f"{base_url}?p_nccObsCode={obs_code}&p_display_type=dailyDataFile&p_stn_num={station_number}"

        rainfall_df["RainfallURL"] = rainfall_df["Site"].astype(str).apply(lambda x: build_url(x, 136))
        temperature_df["MaxTempURL"] = temperature_df["Site"].astype(str).apply(lambda x: build_url(x, 122))
        temperature_df["MinTempURL"] = temperature_df["Site"].astype(str).apply(lambda x: build_url(x, 123))

        return rainfall_df, temperature_df

    def check_zip_existence(self, rainfall_df, temperature_df):
        """Checks if ZIP files already exist."""
        zip_files = set(os.listdir(self.download_dir))

        def zip_exists(station_number, data_type_code):
            return f"IDCJAC{data_type_code}_{station_number}_1800.zip" in zip_files

        rainfall_df["ZipExists"] = rainfall_df["Site"].astype(str).apply(lambda x: zip_exists(x, "0009"))
        temperature_df["MaxZipExists"] = temperature_df["Site"].astype(str).apply(lambda x: zip_exists(x, "0010"))
        temperature_df["MinZipExists"] = temperature_df["Site"].astype(str).apply(lambda x: zip_exists(x, "0011"))

        return rainfall_df, temperature_df

    

    
    def download_missing_files(self, rainfall_df, temperature_df):
        """Downloads missing files using multithreading for faster execution."""
        urls_to_download = []

        # Collect URLs for missing files
        for _, row in rainfall_df.iterrows():
            if not row["ZipExists"]:
                urls_to_download.append(row["RainfallURL"])

        for _, row in temperature_df.iterrows():
            if not row["MaxZipExists"]:
                urls_to_download.append(row["MaxTempURL"])
            if not row["MinZipExists"]:
                urls_to_download.append(row["MinTempURL"])

        # Define the number of threads (adjust based on system resources)
        max_threads = min(7, len(urls_to_download))  # Use up to 5 threads or total URLs if fewer

        # Use multithreading to download files
        with ThreadPoolExecutor(max_threads) as executor:
            executor.map(self.download_weather_data, urls_to_download)

        print("All missing files have been downloaded.")


    
    def download_weather_data(self, url):
        """Downloads BOM weather data while avoiding HTTP 403 errors."""
    
        options = webdriver.FirefoxOptions()
        options.add_argument('--headless')  # Run without opening a browser window
        options.set_preference("general.useragent.override", 
                               "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
    
        browser = webdriver.Firefox(options=options)
    
        try:
            print(f"Accessing {url}...")
            browser.get(url)
            time.sleep(3)  # Allow page to load

            if "temporarily unavailable" in browser.page_source.lower():
                print(f"No data available for {url}")
                self.log_update(f"No data available: {url}")
                return None

            # Find and click "All years of data" link
            try:
                all_years_link = browser.find_element(By.LINK_TEXT, "All years of data")
                file_url = all_years_link.get_attribute("href")
                print(f"Downloading from {file_url}")

                # Set headers to avoid 403
                HEADERS = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    "Referer": url,
                    "Accept-Language": "en-US,en;q=0.9",
                    "Connection": "keep-alive"
                }
            
                req = urllib.request.Request(file_url, headers=HEADERS)
                response = urllib.request.urlopen(req)

                # Extract filename from the headers
                content_disposition = response.info().get('Content-Disposition')
                if content_disposition:
                    filename = re.findall("filename=(.+)", content_disposition)[0]
                else:
                    filename = file_url.split("/")[-1]  # Fallback filename

                filepath = os.path.join(self.download_dir, filename)

                os.makedirs(self.download_dir, exist_ok=True)

                # Save the file
                with open(filepath, 'wb') as f:
                    f.write(response.read())

                print(f"Downloaded: {filename}")
                self.log_update(f"Downloaded: {url} -> {filename}")

                return filename

            except NoSuchElementException:
                print(f"Could not find download link for {url}. Retrying...")
                time.sleep(5)
                browser.refresh()
                return None

        except Exception as e:
            print(f"Error downloading {url}: {e}")
            self.log_update(f"Error: {e}")
            return None

        finally:
            browser.quit()
    

    def log_update(self, message):
        """Logs updates to a file."""
        with open(self.log_file, 'a') as file:
            file.write(message + '\n')

    def close(self):
        if self.connection_pool:
            self.connection_pool.closeall()

if __name__ == "__main__":
    config = load_config()
    paths = get_paths(config)
    conn_params = get_db_params(config)
    download_log = paths.get('download_log', paths.get('log_file', 'updater.log'))
    download_dir = paths.get('zip_dir', 'newzips')
    year = 2023

    updater = StationUpdater(conn_params, download_log, download_dir, year)

    rainfall_df = updater.process_data(
        "http://www.bom.gov.au/climate/data/lists_by_element/numAUS_139.txt",
        "rainfall",
    )
    temperature_df = updater.process_data(
        "http://www.bom.gov.au/climate/data/lists_by_element/alphaAUS_3.txt",
        "temperature",
    )

    rainfall_df, temperature_df = updater.check_zip_existence(rainfall_df, temperature_df)
    rainfall_df, temperature_df = updater.generate_bom_urls(rainfall_df, temperature_df)

    print("Updated Rainfall Data:")
    print(rainfall_df.head())  # Show only first 5 rows

    print("\nUpdated Temperature Data:")
    print(temperature_df.head())

    updater.download_missing_files(rainfall_df, temperature_df)

    updater.close()
