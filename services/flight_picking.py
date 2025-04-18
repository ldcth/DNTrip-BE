import json
import os
import re
from datetime import datetime
import traceback # Added for better error logging

FLIGHT_DATA_DIR = "../scrapper/data/flights" # Relative path from services directory

# --- New Date Parsing Function ---
def parse_date_string(date_str: str) -> str | None:
    """
    Parses a date string in various formats (DD/MM/YYYY, YYYY-MM-DD, Month DD, YYYY, etc.)
    and returns it in ISO format (YYYY-MM-DD).
    Handles month names (abbreviated and full). Returns None if parsing fails.
    """
    date_str = date_str.strip()
    formats_to_try = [
        "%d/%m/%Y",  # 19/04/2025
        "%Y-%m-%d",  # 2025-04-19
        "%b %d, %Y", # Apr 19, 2025
        "%B %d, %Y", # April 19, 2025
        "%d %b %Y",  # 19 Apr 2025
        "%d %B %Y",  # 19 April 2025
        # Add more formats if needed
    ]
    for fmt in formats_to_try:
        try:
            # Attempt to parse the date
            date_obj = datetime.strptime(date_str, fmt)
            return date_obj.strftime("%Y-%m-%d")
        except ValueError:
            continue # Try the next format

    # Handle cases like "April 19th 2025" by removing "st", "nd", "rd", "th"
    date_str_cleaned = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", date_str, flags=re.IGNORECASE)
    if date_str_cleaned != date_str:
         for fmt in formats_to_try:
             try:
                 date_obj = datetime.strptime(date_str_cleaned, fmt)
                 return date_obj.strftime("%Y-%m-%d")
             except ValueError:
                 continue

    print(f"Warning: Could not parse date string '{date_str}' with known formats.")
    return None

# --- Modified get_flights Function ---
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

    # 3. Construct filename and check existence
    filename = f"{origin_code}_{date_iso}.json"
    # Adjust path relative to *this* file's location
    current_dir = os.path.dirname(__file__)
    filepath = os.path.join(current_dir, FLIGHT_DATA_DIR, filename)
    print(f"Looking for flight data file: {filepath}")

    if not os.path.exists(filepath):
        return {"message": f"Sorry, I don't have flight data for {origin_city} ({origin_code}) on {date_iso}."}

    # 4. Load and return data
    try:
        with open(filepath, 'r', encoding='utf-8') as f: # Added encoding
            data = json.load(f)

        if isinstance(data, list):
            flights_to_show = data[:10]
            # TODO: Future enhancement - filter by destination if destination info is available in query/data
            return {"flights": flights_to_show}
        elif isinstance(data, dict) and 'flights' in data and isinstance(data['flights'], list):
             return {"flights": data['flights'][:10]}
        else:
            print(f"Warning: Unexpected data structure in {filename}.")
            return {"error": "Could not process the flight data file due to unexpected structure."}

    except json.JSONDecodeError as e:
        print(f"Error: Could not decode JSON from {filename}. Error: {e}")
        return {"error": f"Error reading flight data file {filename}. It might be corrupted."}
    except Exception as e:
        print(f"An unexpected error occurred while processing {filename}: {e}")
        traceback.print_exc()
        return {"error": "An internal error occurred while retrieving flight data."}

# --- Updated Test Code ---
if __name__ == "__main__":
    test_cases = [
        ("Hanoi", "19/04/2025"),          # Standard format, existing data
        ("Ho Chi Minh City", "April 20, 2025"), # Month name, existing data
        ("Hanoi", "2025-12-25"),          # ISO format, non-existing date
        ("London", "19/04/2025"),         # Unknown origin
        ("Hanoi", "19th April 2025"),     # Date with "th"
        ("Hanoi", "invalid-date"),       # Invalid date format
        ("Da Nang", "20/04/2025")         # Da Nang origin (assuming no DAD file exists yet)
    ]

    for origin, date_str in test_cases:
        print(f"--- Testing Origin: '{origin}', Date: '{date_str}' ---")
        result = get_flights(origin, date_str)
        # Use ensure_ascii=False for potentially non-ASCII characters in flight data
        print(json.dumps(result, indent=2, ensure_ascii=False))
        print("-" * 20)

    # Test directly parsing a query string (previous functionality removed)
    # print("--- Testing query parsing (removed functionality) ---")
    # query = "Show me flights from Hanoi on 19/04/2025?"
    # print(f"Query: {query}")
    # print("Note: Raw query parsing is now handled by the agent's LLM, not this function directly.")
    # print("-" * 20)
