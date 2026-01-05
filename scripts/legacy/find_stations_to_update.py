from scr.config import get_db_params, get_paths, load_config
from scr.station_updater import StationUpdater


def main():
    config = load_config()
    conn_params = get_db_params(config)
    paths = get_paths(config)
    log_file = paths.get('log_file', 'updatelog.txt')
    download_dir = paths.get('zip_dir', 'newzips')
    year = 2023

    # Initialize the StationUpdater
    updater = StationUpdater(conn_params, log_file, download_dir, year)

    try:
        stations_to_update = updater.find_stations_to_update()
        all_stations = updater.get_current_stations()

        if stations_to_update:
            print("Stations that need updating:")
            for station in sorted(stations_to_update):
                print(f"- Station Number: {station}")
            print(f"\nTotal number of stations that need updating: {len(stations_to_update)}")
        else:
            print("All stations are up to date!")

        already_done = set(all_stations) - set(stations_to_update)
        if already_done:
            print("\nStations already done:")
            for station in sorted(already_done):
                print(f"- Station Number: {station}")
            print(f"\nTotal number of stations already done: {len(already_done)}")
        else:
            print("\nNo stations are fully processed yet.")

        db_stations = updater.get_current_stations()
        processed_stations = updater.read_processed_urls()
        downloaded_stations = updater.check_downloaded_files()

        print(f"\nStations fetched from database: {len(db_stations)}")
        print(f"Stations processed from log file: {len(processed_stations)}")
        print(f"Stations found in downloaded files: {len(downloaded_stations)}")

        stations_to_update = updater.find_stations_to_update()
        print(f"\nStations to update: {len(stations_to_update)}")
        print(f"Total stations to update: {len(stations_to_update)}")
    finally:
        updater.close()

if __name__ == "__main__":
    main()
