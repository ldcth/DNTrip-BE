import selenium # Added for type hints potentially
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException, TimeoutException # Added
import time
import json
# from collections import deque # Removed
import re
import logging # Added
import os # Added

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Get the absolute path of the directory the script is in
script_dir = os.path.dirname(os.path.abspath(__file__))

class GoogleMapsCrawler:
    def __init__(self, hotels_file="../data/hotels.json"): # Modified signature
        opts = Options()
        # opts.add_argument("--headless=new") # Consider running headless
        opts.add_argument("--window-size=1920,1080") # Good practice
        # opts.add_argument("--headless=false") # Removed
        self.driver = webdriver.Chrome(options=opts) # Pass options here
        self.wait = WebDriverWait(self.driver, 15) # Increased default wait
        self.hotels_file = hotels_file
        self.hotels_data = self.load_hotels()
        # Removed unused attributes: start_point, initial_URL, starting_coordinate, keywords, current_keyword, list_location_gotten, list_needed_get

    def load_hotels(self):
        """Loads hotel data from the JSON file."""
        try:
            with open(self.hotels_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logging.info(f"Successfully loaded {len(data)} hotels from {self.hotels_file}")
                # Ensure lat/lon keys exist, initialize if not
                for hotel in data:
                    if "lat" not in hotel:
                        hotel["lat"] = None
                    if "lon" not in hotel:
                        hotel["lon"] = None
                return data
        except FileNotFoundError:
            logging.error(f"Error: Input file not found at {self.hotels_file}")
            return []
        except json.JSONDecodeError:
            logging.error(f"Error: Could not decode JSON from {self.hotels_file}")
            return []
        except Exception as e:
            logging.error(f"An unexpected error occurred loading hotels: {e}")
            return []

    # Removed get_list_view_info method
    # Removed get_detail_view_info method

    def get_coordinates_for_hotel(self, hotel_name):
        """Searches for a hotel on Google Maps and extracts coordinates from the URL."""
        logging.info(f"Searching for coordinates for: {hotel_name}")
        try:
            # Navigate to Google Maps for each search to ensure a clean state
            self.driver.get("https://www.google.com/maps")
            search_box = self.wait.until(EC.presence_of_element_located(
                (By.NAME, "q")))
            search_box.clear()
            search_box.send_keys(hotel_name)
            search_box.send_keys(Keys.RETURN)

            # Wait for the URL to likely contain the coordinates
            # This is a bit heuristic; we wait for '@' which is typical in place URLs
            self.wait.until(EC.url_contains("@"))
            time.sleep(2) # Add a small buffer for the URL to fully stabilize

            current_url = self.driver.current_url
            logging.debug(f"Current URL: {current_url}")

            # Regex to find latitude and longitude in the URL path segment like /@lat,lon,zoomz
            match = re.search(r"/@(-?\d+\.\d+),(-?\d+\.\d+),(\d+)", current_url)

            if match:
                lat = match.group(1)
                lon = match.group(2)
                logging.info(f"Found coordinates for {hotel_name}: Lat={lat}, Lon={lon}")
                return lat, lon
            else:
                logging.warning(f"Could not extract coordinates from URL for {hotel_name}. URL: {current_url}")
                return None, None

        except TimeoutException:
            logging.error(f"Timeout occurred while searching for or waiting for URL update for: {hotel_name}")
            # Capture screenshot on error
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            filename = f"error_timeout_{hotel_name.replace(' ', '_')}_{timestamp}.png"
            try:
                self.driver.save_screenshot(filename)
                logging.info(f"Screenshot saved: {filename}")
            except Exception as screen_err:
                logging.error(f"Failed to save screenshot: {screen_err}")
            return None, None
        except NoSuchElementException:
            logging.error(f"Could not find the search box for: {hotel_name}")
            return None, None
        except Exception as e:
            logging.error(f"An unexpected error occurred getting coordinates for {hotel_name}: {e}")
            # Capture screenshot on error
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            filename = f"error_unexpected_{hotel_name.replace(' ', '_')}_{timestamp}.png"
            try:
                self.driver.save_screenshot(filename)
                logging.info(f"Screenshot saved: {filename}")
            except Exception as screen_err:
                logging.error(f"Failed to save screenshot: {screen_err}")
            return None, None

    # Renamed start_crawl to update_hotel_coordinates and modified its logic
    def update_hotel_coordinates(self):
        """Iterates through hotels, gets coordinates, and updates the data."""
        if not self.hotels_data:
            logging.warning("No hotel data loaded, exiting.")
            return

        updated_count = 0
        for i, hotel in enumerate(self.hotels_data):
            # Skip if coordinates already exist and are not None
            if hotel.get("lat") and hotel.get("lon"):
                 logging.info(f"Skipping '{hotel.get('name', 'N/A')}' - coordinates already exist.")
                 continue

            hotel_name = hotel.get("name")
            if not hotel_name or hotel_name == "N/A":
                logging.warning(f"Skipping hotel index {i} due to missing or invalid name.")
                continue

            lat, lon = self.get_coordinates_for_hotel(hotel_name)

            if lat and lon:
                self.hotels_data[i]["lat"] = lat
                self.hotels_data[i]["lon"] = lon
                updated_count += 1
                # Save incrementally after each successful update
                self.save_updated_hotels()
            else:
                # Keep existing None or N/A values if search failed
                logging.warning(f"Failed to get coordinates for '{hotel_name}'. Keeping existing values.")

            # Add a small delay between searches to avoid potential rate limiting
            time.sleep(1)

        logging.info(f"Finished processing. Updated coordinates for {updated_count} hotels.")
        self.save_updated_hotels() # Final save
        self.driver.quit()
        logging.info("WebDriver closed.")

    # Removed crawl_keyword method

    def save_updated_hotels(self):
        """Saves the updated hotel data back to the JSON file."""
        try:
            # Create backup before overwriting
            backup_file = self.hotels_file + ".bak"
            if os.path.exists(self.hotels_file):
                os.replace(self.hotels_file, backup_file) # More atomic than copy/delete
                logging.info(f"Created backup: {backup_file}")

            with open(self.hotels_file, 'w', encoding='utf-8') as f:
                json.dump(self.hotels_data, f, ensure_ascii=False, indent=2)
            logging.info(f"Successfully saved updated hotel data to {self.hotels_file}")
        except IOError as e:
            logging.error(f"Error saving data to {self.hotels_file}: {e}")
        except Exception as e:
            logging.error(f"An unexpected error occurred during saving: {e}")


if __name__ == "__main__":
    # Ensure the path is correct relative to where you run the script
    # If hello.py is in scrapper/ and hotels.json is in data/ (relative to project root)
    # And you run from the project root: python scrapper/hello.py
    # hotels_json_path = "data/hotels.json"
    # If you run from the scrapper/ directory: python hello.py
    # hotels_json_path = "../data/hotels.json" # Path relative to hello.py
    # hotels_json_path = "hotels.json" # Path relative to hello.py

    # Construct the absolute path to hotels.json relative to this script's location
    hotels_json_path = os.path.join(script_dir, "hotels.json")

    if not os.path.exists(hotels_json_path):
         # Use the absolute path in the error message for clarity
         logging.error(f"FATAL: hotels.json not found at the expected path: {hotels_json_path}")
         logging.error("Please ensure the file exists and the path is correct.")
    else:
        crawler = GoogleMapsCrawler(hotels_file=hotels_json_path)
        crawler.update_hotel_coordinates()
