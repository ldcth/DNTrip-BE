import json
import os
import re
from datetime import datetime
import traceback # Added for better error logging
from pymongo.mongo_client import MongoClient
import pymongo
from dotenv import load_dotenv
load_dotenv()

FLIGHT_DATA_DIR = "../scrapper/data/flights" # Relative path from services directory

def get_mongodb_client():
    client = MongoClient(os.getenv('MONGODB_URI'))
    db = client["dntrip"]
    return db["flight_data"]

# --- New Date Parsing Function ---
def parse_date_string(date_str: str) -> str | None:
    """
    Parses a date string in various formats (DD/MM/YYYY, YYYY-MM-DD, Month DD, YYYY, DD/MM, Month DD etc.)
    and returns it in ISO format (YYYY-MM-DD).
    Handles month names (abbreviated and full). Assumes year 2025 if not provided.
    Returns None if parsing fails.
    """
    date_str = date_str.strip()
    DEFAULT_YEAR = 2025
    formats_to_try = [
        # Formats with year (priority)
        ("%d/%m/%Y", False),
        ("%Y-%m-%d", False),
        ("%b %d, %Y", False),
        ("%B %d, %Y", False),
        ("%d %b %Y", False),
        ("%d %B %Y", False),

        # Formats without year (will default to DEFAULT_YEAR)
        # Assuming DD/MM for numeric only based on existing DD/MM/YYYY
        ("%d/%m", True),      # e.g. 19/04
        ("%b %d", True),      # e.g. Apr 19
        ("%B %d", True),      # e.g. April 19
        ("%d %b", True),      # e.g. 19 Apr
        ("%d %B", True),      # e.g. 19 April
    ]

    # Attempt parsing with original string
    for fmt, assume_default_year in formats_to_try:
        try:
            date_obj = datetime.strptime(date_str, fmt)
            if assume_default_year:
                # If strptime defaults to year 1900 for formats like %m/%d,
                # or if we explicitly know the format lacks a year.
                date_obj = date_obj.replace(year=DEFAULT_YEAR)
            return date_obj.strftime("%Y-%m-%d")
        except ValueError:
            continue

    # Handle cases like "April 19th 2025" or "April 19th" by removing "st", "nd", "rd", "th"
    date_str_cleaned = re.sub(r"(\d+)(st|nd|rd|th)", r"\\1", date_str, flags=re.IGNORECASE)
    if date_str_cleaned != date_str: # Only proceed if cleaning changed the string
         for fmt, assume_default_year in formats_to_try:
             try:
                 date_obj = datetime.strptime(date_str_cleaned, fmt)
                 if assume_default_year:
                     date_obj = date_obj.replace(year=DEFAULT_YEAR)
                 return date_obj.strftime("%Y-%m-%d")
             except ValueError:
                 continue

    print(f"Warning: Could not parse date string '{date_str}' with known formats.")
    return None

# --- Function to get flights from JSON (preserved) ---
def _get_flights_from_json_file(origin_city: str, origin_code: str, date_iso: str) -> dict:
    """
    Gets flight information from a local JSON file.
    (Original file-reading logic preserved here)
    """
    filename = f"{origin_code}_{date_iso}.json"
    # Adjust path relative to *this* file's location
    current_dir = os.path.dirname(__file__)
    filepath = os.path.join(current_dir, FLIGHT_DATA_DIR, filename)
    print(f"Looking for flight data file (JSON source): {filepath}")

    if not os.path.exists(filepath):
        return {"message": f"Sorry, I don't have flight data (from JSON file) for {origin_city} ({origin_code}) on {date_iso}."}

    # 4. Load and return data
    try:
        with open(filepath, 'r', encoding='utf-8') as f: # Added encoding
            data = json.load(f)

        if isinstance(data, list):
            flights_to_show = data[:10]
            # Add source identifier
            return {"source": "json", "flights": flights_to_show}
        elif isinstance(data, dict) and 'flights' in data and isinstance(data['flights'], list):
             # Add source identifier
             return {"source": "json", "flights": data['flights'][:10]}
        else:
            print(f"Warning: Unexpected data structure in {filename}.")
            return {"error": "Could not process the JSON flight data file due to unexpected structure."}

    except json.JSONDecodeError as e:
        print(f"Error: Could not decode JSON from {filename}. Error: {e}")
        return {"error": f"Error reading JSON flight data file {filename}. It might be corrupted."}
    except Exception as e:
        print(f"An unexpected error occurred while processing {filename} (JSON): {e}")
        traceback.print_exc()
        return {"error": "An internal error occurred while retrieving flight data from JSON."}

# --- Function to get flights from MongoDB ---
def get_flight_data_from_db(origin_code: str, date_iso: str) -> dict:
    """
    Gets flight data from MongoDB based on origin airport code and date.
    """
    collection = get_mongodb_client()
    if collection is None:
        return {"error": "Database connection failed. Cannot retrieve flight data."}

    # Match the date format used in your DB (assuming it's YYYY-MM-DD)
    # If your DB stores dates differently, adjust the query format here.
    # Assuming 'departure_airport_code' and 'search_date' are the correct DB fields based on current code
    query = {"departure_airport_code": origin_code, "search_date": date_iso}
    # Corrected projection: Exclude _id and use rename syntax based on current query fields
    projection = {
        "_id": 0,                      # EXCLUDE _id for JSON compatibility
        "price": "$price",              # Assumes DB field is 'price'
        "date": "$date",                # Assumes DB field is 'date'
        "flight_id": "$flight_id",      # Assumes DB field is 'flight_id'
        "flight_time": "$flight_time",    # Assumes DB field is 'flight_time'
        "departure_airport": "$departure_airport", # Assumes DB field is 'departure_airport'
        "departure_time": "$departure_time", # Assumes DB field is 'departure_time'
        "arrival_airport": "$arrival_airport",   # Assumes DB field is 'arrival_airport'
        "arrival_time": "$arrival_time",     # Assumes DB field is 'arrival_time'
        "departure_airport_code": "$departure_airport_code", # Keep as is
        "arrival_airport_code": "$arrival_airport_code",   # Assumes DB field is 'arrival_airport_code'
        "search_date": "$search_date"      # Keep as is
    }

    try:
        print(f"Querying MongoDB: Collection='{collection.name}', Query={query}") # Removed projection from log for brevity
        # Add limit to avoid fetching excessive data, adjust as needed
        cursor = collection.find(query, projection).limit(20) # Limit query size
        # CRITICAL FIX: Ensure cursor is consumed into a list *before* returning
        flights = list(cursor) # Execute query and convert to list
        print(f"Flights found: {len(flights)}") # Optional: Log how many flights were found

        if not flights:
            # More specific message
            return {"message": f"No flights found in database matching origin '{origin_code}' and date '{date_iso}'."}
        else:
             # Limit to 10 flights for the final response if more were found
             return {"source": "mongodb", "flights": flights[:10]}

    except pymongo.errors.PyMongoError as e:
        print(f"Error querying MongoDB: {e}")
        traceback.print_exc()
        return {"error": "An error occurred while querying the flight database."}
    except Exception as e:
        print(f"An unexpected error occurred during DB query: {e}")
        traceback.print_exc()
        return {"error": "An internal error occurred while retrieving flight data from DB."}

# --- Modified get_flights Function (Now uses MongoDB primarily) ---
def get_flights(origin_city: str, date_str: str) -> dict:
    """
    Gets flight information for a specific origin city and date.

    Args:
        origin_city: The name of the origin city (e.g., "Hanoi", "Ho Chi Minh City").
        date_str: The desired date string in a recognizable format (e.g., "19/04/2025", "April 19, 2025").

    Returns:
        A dictionary containing either the flight data (up to 10 flights)
        or an error/message.
    """
    print(f"--- Getting flights for Origin: {origin_city}, Date String: {date_str} ---")

    # 1. Map origin city name to code
    origin_map = {
        "HANOI": "HAN",
        "HCM": "SGN",
        "HA NOI": "HAN",
        "HO CHI MINH CITY": "SGN",
        "SAIGON": "SGN",
        "DA NANG": "DAD"
    }
    origin_code = origin_map.get(origin_city.strip().upper())

    # Handle variations if direct map fails
    if not origin_code:
        upper_origin = origin_city.strip().upper()
        if upper_origin == "HOCHIMINH CITY":
             origin_code = origin_map.get("HO CHI MINH CITY")
        elif upper_origin == "DANANG":
             origin_code = origin_map.get("DA NANG")

    if not origin_code:
        return {"error": f"Sorry, I don't recognize the origin city '{origin_city}'. Please use known cities like Hanoi, Ho Chi Minh City, Da Nang."}

    # 2. Parse the date string
    date_iso = parse_date_string(date_str)
    if not date_iso:
        return {"error": f"Sorry, I couldn't understand the date '{date_str}'. Please use formats like DD/MM/YYYY, YYYY-MM-DD, or Month DD, YYYY."}

    # 3. Fetch data from MongoDB
    print(f"Attempting to fetch data from MongoDB for {origin_code} on {date_iso}")
    db_result = get_flight_data_from_db(origin_code, date_iso)
    # db_result = _get_flights_from_json_file(origin_city, origin_code, date_iso)

    return db_result # Return result primarily from MongoDB

# --- Updated Test Code ---
if __name__ == "__main__":
    # Ensure environment variables for MongoDB are set if needed,
    # or modify the placeholder values above.
    # Example using dotenv:
    # from dotenv import load_dotenv
    # load_dotenv() # Load .env file if it exists

    print("--- Running Test Cases (using MongoDB primarily) ---")

    test_cases = [
        ("Hanoi", "25/04/2025"),          # Assumes data exists in DB for this
        # ("Ho Chi Minh City", "April 24, 2025"), # Assumes data exists in DB for this
        # ("Hanoi", "2025-12-25"),          # Assumes no data exists in DB
        # ("London", "19/04/2025"),         # Unknown origin
        ("Hanoi", "19th April 2025"),     # Date with "th", with year
        ("Hanoi", "19th April"),          # Date with "th", no year -> should be 2025-04-19
        ("Hanoi", "invalid-date"),       # Invalid date format
        # ("Da Nang", "20/04/2025")         # Assumes data exists in DB for DAD

        # New test cases for day/month input with default year 2025
        ("Hanoi", "25/04"),               # DD/MM -> should be 2025-04-25
        ("Hanoi", "Apr 26"),              # Mon DD -> should be 2025-04-26
        ("Hanoi", "27 Apr"),              # DD Mon -> should be 2025-04-27
        ("Saigon", "May 10"),             # Test with another city and month name -> 2025-05-10
        ("Da Nang", "15/11"),             # Test another city DD/MM -> 2025-11-15
    ]

    for origin, date_str in test_cases:
        print(f"--- Testing Origin: '{origin}', Date: '{date_str}' ---")
        result = get_flights(origin, date_str)
        # Use ensure_ascii=False for potentially non-ASCII characters in flight data
        print(json.dumps(result, indent=2, ensure_ascii=False))
        print("-" * 20)

