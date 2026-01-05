import time
import re
import urllib.request
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
import psycopg2
from scr.config import get_db_params, get_paths, load_config

CONFIG = load_config()
DB_CONNECTION_PARAMS = get_db_params(CONFIG)
PATHS = get_paths(CONFIG)
DOWNLOAD_DIR = PATHS.get('zip_dir', 'newzips')
LOG_FILE_PATH = PATHS.get('log_file', 'updatelog.txt')


def ensure_parent_directory(path: str) -> None:
    """Ensure the directory for the provided path exists."""
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)


os.makedirs(DOWNLOAD_DIR, exist_ok=True)
ensure_parent_directory(LOG_FILE_PATH)


def get_current_stations(conn_params):
    # Connect to the PostgreSQL database
    connection = psycopg2.connect(**conn_params)
    cursor = connection.cursor()

    try:
        # Define the current date as of January 2023
        the_year = 2023

        # Execute the SQL query to get current stations
        query = """
            SELECT bom_station_number
            FROM station
            WHERE start_year <= %s AND (end_year IS NULL OR end_year >= %s)
        """
        cursor.execute(query, (the_year, the_year))

        # Fetch all rows from the result set
        station_numbers = [row[0] for row in cursor.fetchall()]

        return station_numbers

    finally:
        # Close the cursor and connection
        cursor.close()
        connection.close()


def generate_bom_urls(station_number):
    base_url = "http://www.bom.gov.au/jsp/ncc/cdio/weatherData/av"
    obs_codes = [122, 123, 136]
    
    return [f"{base_url}?p_nccObsCode={code}&p_display_type=dailyDataFile&p_stn_num={station_number}" for code in obs_codes]





def download_weather_data(url):
     # Set user agent to Firefox to avoid bot detection
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:100.0) Gecko/20100101 Firefox/100.0"

    # Set Firefox options
    options = webdriver.FirefoxOptions()
    options.set_preference("general.useragent.override", user_agent)
    options.add_argument('--headless')

    # Launch Firefox browser
    browser = webdriver.Firefox(options=options)

    # Navigate to the website
    browser.get(url)
    

    # Check if the page title is "Weather Data temporarily unavailable"
    if browser.title == 'Weather Data temporarily unavailable':
        print('You have been redirected to a page with the title "Weather Data temporarily unavailable"')
        browser.quit()
        with open(LOG_FILE_PATH, 'a') as file:
            file.write('No data available at ')
            file.write(url + '\n')
        return None

    while True:
        try:
            # Find the link for "All years of data"
            all_years_link = browser.find_element(By.LINK_TEXT,"All years of data")
            # Download the file from the link
            file_url = all_years_link.get_attribute("href")
            user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
            req = urllib.request.Request(file_url, headers={'User-Agent': user_agent})
            response = urllib.request.urlopen(req)

            # Extract the filename from the Content-Disposition header
            content_disposition = response.info().get('Content-Disposition')
            filename = re.findall("filename=(.+)", content_disposition)[0]

            filepath = os.path.join(DOWNLOAD_DIR, filename)

            # Save the file in the "zips" directory
            with open(filepath, 'wb') as f:
                f.write(response.read())

            # Close the browser
            browser.quit()

            with open(LOG_FILE_PATH, 'a') as file:
                file.write(url + ',')
                file.write(filename + '\n')
                

            print(filename)
            return filename

        except NoSuchElementException:
            print("All years of data link not found. Refreshing page...")
            browser.refresh()
            time.sleep(5)  # Wait for page to load before trying again
            continue


# this is for checking the log file in order to restart the script where it last failed

def extract_station_numbers_from_urls(urls):
    # Define a regular expression pattern to extract the p_stn_num parameter
    pattern = r"p_stn_num=(\d+)"

    # Initialize an empty set to store unique extracted station numbers
    unique_station_numbers = set()

    # Iterate through each URL in the list
    for url in urls:
        # Use re.search to find the pattern in the URL
        match = re.search(pattern, url)

        # If a match is found, extract the station number and add it to the set
        if match:
            station_number = match.group(1)
            unique_station_numbers.add(station_number)

    # Convert the set back to a list
    return list(unique_station_numbers)



# Read the content of the log file if it exists
if os.path.exists(LOG_FILE_PATH):
    with open(LOG_FILE_PATH, "r") as file:
        # Read each line from the file and store it in a list
        log_urls = file.readlines()
else:
    log_urls = []

# Use the function to extract unique station numbers from the list of URLs
unique_station_numbers = extract_station_numbers_from_urls(log_urls)



current_stations = get_current_stations(DB_CONNECTION_PARAMS)


# Find the stations in the database that are not in the log file
stations_to_get = set(map(str, current_stations)) - set(unique_station_numbers)


print("Number of stations in the list:", len(current_stations))
print("NUmber of stations to get:", len(stations_to_get))

for station_number in stations_to_get:
    urls = generate_bom_urls(station_number)
    for url in urls:
        print(url)
        download_weather_data(url)
        


