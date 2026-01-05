import psycopg2
import csv

class StationDataTypeChecker:
    def __init__(self, csv_file, db_name="bom_clone", user="patrick", host="localhost"):
        """Initialize with CSV file and database connection details."""
        self.csv_file = csv_file
        self.db_name = db_name
        self.user = user
        self.host = host
        self.connection = None

    def connect_db(self):
        """Establish connection to the PostgreSQL database."""
        try:
            self.connection = psycopg2.connect(
                dbname=self.db_name,
                user=self.user,
                host=self.host
            )
            print("Database connection successful.")
        except Exception as e:
            print(f"Database connection failed: {e}")

    def fetch_station_numbers(self):
        """Fetch station numbers from the database."""
        if not self.connection:
            print("No database connection.")
            return set()

        cursor = self.connection.cursor()
        cursor.execute("SELECT DISTINCT station_number FROM station;")  # Adjust table name if needed
        stations = {row[0] for row in cursor.fetchall()}
        cursor.close()
        return stations

    def check_csv_stations(self):
        """Check if station numbers in CSV exist in the database."""
        station_numbers_in_db = self.fetch_station_numbers()
        missing_stations = []

        with open(self.csv_file, 'r') as file:
            reader = csv.reader(file)
            next(reader)  # Skip header
            for row in reader:
                station_number = row[0].strip()  # Assuming station number is in the first column
                if station_number not in station_numbers_in_db:
                    missing_stations.append(station_number)

        if missing_stations:
            print("Missing station numbers:", missing_stations)
        else:
            print("All station numbers are present in the database.")

    def close_connection(self):
        """Close the database connection."""
        if self.connection:
            self.connection.close()
            print("Database connection closed.")

# Usage
csv_file = "output.csv"  # Replace with your actual CSV filename
checker = StationDataTypeChecker(csv_file)
checker.connect_db()
checker.check_csv_stations()
checker.close_connection()
