import selenium
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException
from selenium.webdriver.common.keys import Keys
import time
import json
import re
import os
import logging
from datetime import date, timedelta
from pymongo import MongoClient

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class KayakFlightCrawler:
    def __init__(self, output_dir="scrapper/data/flights"):
        self.driver = webdriver.Chrome()
        self.driver.maximize_window()
        self.wait = WebDriverWait(self.driver, 30) # Increased wait time for Kayak
        self.detail_wait = WebDriverWait(self.driver, 20) # Wait time for detail popup
        self.output_dir = output_dir
        self.scraped_flights = [] # Holds flights for the current run
        self.all_scraped_flights = [] # Holds flights from ALL runs
        self.db = self._get_mongodb_client()
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
            logging.info(f"Created output directory: {self.output_dir}")

    def _get_mongodb_client(self):
        client = MongoClient(os.getenv('MONGODB_URI'))
        db = client["dntrip"]
        return db["flight_data"]
    
    def _get_dates(self):
        """Gets tomorrow's and the day after tomorrow's date."""
        today = date.today()
        tomorrow = today + timedelta(days=1)
        day_after_tomorrow = today + timedelta(days=2)
        return tomorrow.strftime("%Y-%m-%d"), day_after_tomorrow.strftime("%Y-%m-%d")

    def _build_url(self, departure, arrival, date_str):
        """Builds the Kayak search URL."""
        # URL structure based on user input, ensuring sorting and stops parameters
        base_url = f"https://www.kayak.com/flights/{departure}-{arrival}/{date_str}"
        params = "?sort=bestflight_a&fs=stops=-1" # Keep sorting and stops as requested
        return base_url + params

    def _close_dialog_and_return_to_main(self):
        """Closes any open dialog and returns to the main flight list view."""
        try:
            current_url = self.driver.current_url
            if "#dialog" in current_url:
                # Try to close dialog by navigating back to main view
                base_url = current_url.split("#")[0]
                new_url = base_url + "#function"
                logging.info(f"Closing dialog and returning to main view: {new_url}")
                self.driver.get(new_url)
                time.sleep(2)
                return True
            
            # Alternative: Try to find and click close button if it exists
            try:
                close_button = self.driver.find_element(By.XPATH, "//button[contains(@class, 'close') or contains(@aria-label, 'close') or contains(@aria-label, 'Close')]")
                close_button.click()
                time.sleep(1)
                logging.info("Closed dialog using close button.")
                return True
            except NoSuchElementException:
                pass
                
            # Alternative: Press Escape key
            try:
                self.driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                time.sleep(1)
                logging.info("Closed dialog using Escape key.")
                return True
            except:
                pass
                
        except Exception as e:
            logging.warning(f"Error while trying to close dialog: {e}")
            
        return False

    def _scrape_flight_details(self, flight_element):
        """Extracts details from the new flight details view/page."""
        flight_data = {
            'price': "N/A",
            'date': "N/A",
            'flight_id': "N/A", # Will be combination of carrier and flight number
            'flight_time': "N/A", # Duration
            'departure_airport': "N/A",
            'departure_time': "N/A",
            'arrival_airport': "N/A",
            'arrival_time': "N/A",
            'carrier': "N/A", # Added carrier
        }
        
        # It's assumed the driver is now on the new page/view (#dialog)
        # Wait for the main details container of the new view
        details_container_xpath = "//div[@class='E69K-leg-wrapper']" 
        try:
            details_container_element = self.detail_wait.until(
                EC.visibility_of_element_located((By.XPATH, details_container_xpath))
            )
            logging.info("Flight details container (E69K-leg-wrapper) found on new view.")
            time.sleep(0.5) # Allow for content rendering

            # --- Extract Price ---
            # price_xpath = div = jnTP-display-price
            try:
                price_element_xpath = "//div[contains(@class, 'jnTP-display-price')]" # Search globally on the new page
                price_element = self.driver.find_element(By.XPATH, price_element_xpath)
                flight_data['price'] = price_element.text.strip()
                logging.info(f"Found price: {flight_data['price']}")
            except NoSuchElementException:
                logging.warning("Could not find price element with class 'jnTP-display-price'.")

            # --- Extract Date ---
            # Get element with class E69K-sleek-wrapper inside details_container_element, 
            # then get second span in class c2x94-title
            try:
                sleek_wrapper_element = details_container_element.find_element(By.XPATH, ".//div[contains(@class, 'E69K-sleek-wrapper')]")
                title_element = sleek_wrapper_element.find_element(By.XPATH, ".//div[contains(@class, 'c2x94-title')]")
                date_spans = title_element.find_elements(By.XPATH, ".//span")
                if len(date_spans) > 1:
                    flight_data['date'] = date_spans[1].text.strip()
                    logging.info(f"Found date: {flight_data['date']}")
                else:
                    logging.warning("Could not find the second span for date in 'c2x94-title'.")
            except NoSuchElementException:
                logging.warning("Could not find date elements (E69K-sleek-wrapper or c2x94-title).")
            
            # --- Extract details from NxR6 container ---
            # Other elements are inside div with class NxR6 inside details_container_element
            try:
                nxr6_container_xpath_relative = ".//div[@class='NxR6']"
                nxr6_container_element = details_container_element.find_element(By.XPATH, nxr6_container_xpath_relative)
                logging.info("Found NxR6 container for further details.")

                # Flight Times and Duration: div.NxR6-time and span.NxR6-duration
                try:
                    time_element = nxr6_container_element.find_element(By.XPATH, ".//div[@class='NxR6-time']")
                    full_time_text = time_element.text.strip() # e.g., "7:55 pm - 9:15 pm(1h 20m)"
                    
                    # Extract duration
                    duration_match = re.search(r'\((.*?)\)', full_time_text)
                    if duration_match:
                        flight_data['flight_time'] = duration_match.group(1)
                        # Remove duration from full_time_text to parse departure/arrival times
                        time_text_parts = full_time_text.replace(f"({flight_data['flight_time']})", "").strip()
                    else:
                        time_text_parts = full_time_text
                        logging.warning("Could not parse duration from NxR6-time.")
                    
                    # Extract departure and arrival times
                    times = time_text_parts.split('-')
                    if len(times) == 2:
                        flight_data['departure_time'] = times[0].strip()
                        flight_data['arrival_time'] = times[1].strip()
                    else:
                        logging.warning(f"Could not parse departure/arrival times from: {time_text_parts}")
                    logging.info(f"Found times: Dep {flight_data['departure_time']}, Arr {flight_data['arrival_time']}, Dur {flight_data['flight_time']}")
                except NoSuchElementException:
                    logging.warning("Could not find time element (NxR6-time).")

                # Airports: div.NxR6-airport
                try:
                    airport_element = nxr6_container_element.find_element(By.XPATH, ".//div[@class='NxR6-airport']")
                    airport_text = airport_element.text.strip() # e.g., "Noibai (HAN) - Da Nang (DAD)"
                    airports = airport_text.split(' - ')
                    if len(airports) == 2:
                        flight_data['departure_airport'] = airports[0].strip()
                        flight_data['arrival_airport'] = airports[1].strip()
                    else:
                        logging.warning(f"Could not parse departure/arrival airports from: {airport_text}")
                    logging.info(f"Found airports: Dep {flight_data['departure_airport']}, Arr {flight_data['arrival_airport']}")
                except NoSuchElementException:
                    logging.warning("Could not find airport element (NxR6-airport).")

                # Flight ID (Carrier & Number): first div in div.NxR6-plane-details
                try:
                    plane_details_element = nxr6_container_element.find_element(By.XPATH, ".//div[@class='NxR6-plane-details']")
                    # First div child for carrier and number
                    carrier_info_element = plane_details_element.find_element(By.XPATH, "./div[1]") # First div child
                    carrier_text_full = carrier_info_element.text.strip() # e.g., "VietJet Air 1509" or "VietJet Air VJ1509"
                    
                    # Attempt to split carrier name and flight number/ID
                    # This regex tries to capture the last part as flight ID (alphanumeric)
                    # and the preceding part as the carrier.
                    match = re.match(r'^(.*?)\s*([A-Z0-9]+)$', carrier_text_full)
                    if match:
                        flight_data['carrier'] = match.group(1).strip()
                        flight_data['flight_id'] = match.group(2).strip() # This is the flight number part
                    else:
                        # Fallback: assume the whole string is carrier if no clear number, or just use it as flight_id
                        flight_data['carrier'] = carrier_text_full 
                        flight_data['flight_id'] = carrier_text_full # Or set to N/A if preferred
                        logging.warning(f"Could not reliably split carrier and flight number from: {carrier_text_full}. Using full text for carrier and flight_id.")
                    
                    logging.info(f"Found carrier: {flight_data['carrier']}, flight_id (number): {flight_data['flight_id']}")

                except NoSuchElementException:
                    logging.warning("Could not find plane details element (NxR6-plane-details) or carrier info.")
            
            except NoSuchElementException:
                logging.warning("Could not find the main NxR6 container for flight details.")

        except TimeoutException:
            logging.error("Timeout waiting for flight details container (E69K-leg-wrapper) on new view.")
            # self.driver.save_screenshot(f"{self.output_dir}/detail_scrape_timeout_error.png") # Consider adding screenshot for this specific timeout
            return None
        except Exception as e:
            logging.error(f"An unexpected error occurred during detail scraping on new view: {e}", exc_info=True)
            # self.driver.save_screenshot(f"{self.output_dir}/detail_scrape_unexpected_error.png")
            return None

        # Return None if essential data is missing, to avoid partial records
        if flight_data['price'] == "N/A" and flight_data['flight_id'] == "N/A" and flight_data['departure_time'] == "N/A":
            logging.warning("Essential flight data (price, flight_id, departure_time) not found. Discarding entry.")
            return None
            
        return flight_data

    def scrape_flights(self, departure, arrival, date_str, target_count=20):
        """Scrapes flights for a given route and date."""
        search_url = self._build_url(departure, arrival, date_str)
        output_filename = os.path.join(self.output_dir, f"{departure}_{date_str}.json")
        self.scraped_flights = [] # Reset for this specific scrape job

        # Clear the specific output file at the beginning of the run
        if os.path.exists(output_filename):
             logging.warning(f"Output file {output_filename} exists. It will be overwritten.")
             try:
                 os.remove(output_filename)
             except OSError as e:
                 logging.error(f"Could not remove existing file {output_filename}: {e}")
                 return # Stop if file can't be removed

        # Initialize the file with an empty list
        self._save_to_json(output_filename, [])


        logging.info(f"Navigating to: {search_url}")
        self.driver.get(search_url)
        time.sleep(10)
        try:
            # --- Handle Potential Overlays (Cookies, etc.) ---
            # --- Wait for Flight Results ---
            # Use class name Fxw9 for the results container
            results_container_xpath = "//div[contains(@class, 'Fxw9')]" # Find div containing class Fxw9
            logging.info(f"Waiting for results container: {results_container_xpath}")
            # Wait for presence first
            self.wait.until(EC.presence_of_element_located((By.XPATH, results_container_xpath)))
            # Then get the element itself
            results_container_element = self.driver.find_element(By.XPATH, results_container_xpath)
            logging.info("Flight results container element found.")
            time.sleep(2) # Wait for results to render


            # --- Locate Individual Flight Elements ---           
            # Using a relative path from the container element found above
            # Use the specific class name provided by the user
            flight_elements_xpath = ".//div[contains(@class, 'Fxw9-result-item-container')]" 

            last_height = self.driver.execute_script("return document.body.scrollHeight")
            processed_flight_ids = set() # To avoid processing the same flight multiple times if DOM changes

            while len(self.scraped_flights) < target_count:
                logging.info("-" * 20)
                logging.info(f"Current flight count: {len(self.scraped_flights)} / {target_count}")
                new_flights_found_in_pass = False

                try:
                    # Find elements *within* the container
                    flight_elements = results_container_element.find_elements(By.XPATH, flight_elements_xpath)
                    logging.info(f"Found {len(flight_elements)} potential flight elements within container.")

                    if not flight_elements:
                         logging.warning("No flight elements found within container. Check selector or wait conditions.")
                         # Potentially wait longer or check if results actually loaded
                         time.sleep(5)
                         # Re-try finding elements within container
                         flight_elements = results_container_element.find_elements(By.XPATH, flight_elements_xpath)
                         if not flight_elements:
                             logging.error("Still no flight elements found within container. Stopping scrape for this URL.")
                             break
                except StaleElementReferenceException:
                    logging.warning("Results container element became stale. Re-finding container and elements...")
                    try:
                         results_container_element = self.driver.find_element(By.XPATH, results_container_xpath)
                         flight_elements = results_container_element.find_elements(By.XPATH, flight_elements_xpath)
                         logging.info(f"Re-found container and {len(flight_elements)} elements.")
                    except (NoSuchElementException, StaleElementReferenceException) as refind_err:
                         logging.error(f"Could not re-find results container after staleness: {refind_err}")
                         break # Stop if we can't re-find the container
                except Exception as e:
                    logging.error(f"Error finding flight elements within container: {e}")
                    break # Stop if we can't find elements

                for i, element in enumerate(flight_elements):
                    # Create a unique ID for the element based on some attribute or text if possible
                    # This is a basic attempt; a more robust method might be needed
                    try:
                        # Try to get a unique identifier, e.g., the price text or time text as a proxy
                        # This is prone to errors if structure changes or elements are missing
                        unique_id_part1 = element.find_element(By.XPATH, ".//span[contains(@class, 'price-text')]").text # Assuming price is usually present
                        unique_id_part2 = element.find_element(By.XPATH, ".//div[contains(@class, 'times')]//span[@class='depart-time']").text # Assuming departure time is present
                        flight_id = f"{unique_id_part1}_{unique_id_part2}"
                    except Exception:
                        # Fallback if unique parts can't be found, use index (less reliable)
                        flight_id = f"index_{i}"


                    if flight_id not in processed_flight_ids:
                        logging.info(f"Processing potential flight element {i+1} (ID: {flight_id})...")
                        try:
                            # Check if element is visible before interaction
                            if not element.is_displayed():
                                logging.warning(f"Element {i+1} not visible, scrolling.")
                                self.driver.execute_script("arguments[0].scrollIntoViewIfNeeded(true);", element)
                                time.sleep(0.5)

                            # Click the element *before* passing it to the scraping function
                            logging.info(f"Clicking element {i+1} to open details...")
                            element.click()
                            time.sleep(1) # Allow time for popup transition

                            flight_details = self._scrape_flight_details(element)

                            # After scraping details, close dialog and return to main view
                            if self._close_dialog_and_return_to_main():
                                # Re-find the results container after navigation
                                try:
                                    results_container_element = self.driver.find_element(By.XPATH, results_container_xpath)
                                    logging.info("Successfully returned to main view and re-found results container.")
                                except NoSuchElementException:
                                    logging.warning("Could not re-find results container after returning from dialog. Will retry in next iteration.")
                                    break  # Break inner loop to restart element finding
                            else:
                                logging.warning("Failed to close dialog and return to main view. Will continue but may encounter issues.")

                            if flight_details:
                                # Add database-specific keys
                                flight_details['departure_airport_code'] = departure 
                                flight_details['arrival_airport_code'] = arrival
                                flight_details['search_date'] = date_str
                                
                                self.scraped_flights.append(flight_details)
                                processed_flight_ids.add(flight_id) # Mark as processed
                                new_flights_found_in_pass = True
                                logging.info(f"Successfully added flight. Total: {len(self.scraped_flights)}")

                                if len(self.scraped_flights) >= target_count:
                                    logging.info(f"Reached target count of {target_count}.")
                                    break # Exit inner loop (element processing)
                            else:
                                logging.warning(f"Failed to extract details for element {i+1}. Skipping.")
                                # Mark potentially problematic elements to avoid retrying infinitely
                                processed_flight_ids.add(flight_id)


                        except StaleElementReferenceException:
                             logging.warning(f"Stale element reference for element {i+1}. Re-finding elements might be needed.")
                             # Break the inner loop to re-fetch elements in the outer loop
                             break
                        except Exception as e:
                            logging.error(f"Unexpected error processing element {i+1}: {e}")
                            # Mark as processed to avoid retrying problematic element
                            processed_flight_ids.add(flight_id)
                    else:
                        logging.info(f"Skipping already processed flight element (ID: {flight_id}).")


                # Check if target reached after processing current view
                if len(self.scraped_flights) >= target_count:
                    break # Exit outer loop (scrolling/pagination)


                # --- Scrolling Logic (if needed) ---
                logging.info("Scrolling down to check for more results...")
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(3) # Wait for potential new content to load

                new_height = self.driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    logging.info("Scroll height did not change. Assuming end of results.")
                    break # Exit outer loop if no more content loads
                last_height = new_height

                # Optional: Add a check here if !new_flights_found_in_pass after a scroll
                # If scroll happened but no new unique flights were processed, maybe break


        except TimeoutException as e:
            logging.error(f"Timeout waiting for elements on {search_url}: {e}")
            self.driver.save_screenshot(f"{self.output_dir}/timeout_error_{departure}_{date_str}.png")
        except Exception as e:
            logging.critical(f"A critical error occurred during scraping {search_url}: {e}", exc_info=True)
            self.driver.save_screenshot(f"{self.output_dir}/critical_error_{departure}_{date_str}.png")
        finally:
            logging.info(f"Finished scraping for {departure} to {arrival} on {date_str}.")
            logging.info(f"Total flights scraped for this run: {len(self.scraped_flights)}")
            
            # --- Deduplication Logic ---
            seen_keys = set()
            deduplicated_list = []
            logging.info(f"Starting deduplication of {len(self.scraped_flights)} scraped flights...")
            for flight in self.scraped_flights:
                # Use a key sensitive to specific flight details to identify duplicates
                key = (
                    flight.get('flight_id', 'N/A'),
                    flight.get('departure_time', 'N/A'),
                    flight.get('arrival_time', 'N/A'),
                    flight.get('departure_airport', 'N/A'), # Use original key for deduplication
                    flight.get('arrival_airport', 'N/A'),   # Use original key for deduplication
                    flight.get('price', 'N/A'), # Consider adding price to key? Maybe not, as it can fluctuate
                    flight.get('search_date', date_str) # Include search date for context
                )
                if key not in seen_keys:
                    seen_keys.add(key)
                    deduplicated_list.append(flight)
                else:
                    logging.debug(f"Duplicate detected and skipped: {key}") # Log duplicates at debug level
            logging.info(f"Finished deduplication. Unique flights: {len(deduplicated_list)}")
            
            # --- Accumulate results for final DB insertion --- 
            self.all_scraped_flights.extend(deduplicated_list)
            logging.info(f"Added {len(deduplicated_list)} unique flights to the main accumulator. Total accumulated: {len(self.all_scraped_flights)}")

            # --- Save to JSON (Keep this per-run) ---
            self._save_to_json(output_filename, deduplicated_list) # Call renamed method with deduplicated data

    def _save_to_json(self, filename, data_list):
        """Saves the provided data list to the specified JSON file."""
        # This method now accepts the data list directly
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data_list, f, ensure_ascii=False, indent=2)
            logging.info(f"Saved {len(data_list)} unique flights to {filename}")
        except IOError as e:
            logging.error(f"Error saving data to {filename}: {e}")

    def _update_database(self, all_flights):
        """Deletes all existing data and inserts the provided list of flights into MongoDB."""
        if not all_flights:
            logging.warning("No flights were accumulated, skipping database update.")
            return

        logging.info(f"\n{'='*30}\nAttempting final database update with {len(all_flights)} accumulated flights...\n{'='*30}")
        try:
            # 1. Delete ALL existing data in the collection
            logging.info(f"Deleting ALL existing documents from collection: {self.db.name}...")
            delete_result = self.db.delete_many({})
            logging.info(f"Deleted {delete_result.deleted_count} documents.")

            # 2. Insert all accumulated data
            logging.info(f"Inserting {len(all_flights)} new documents...")
            insert_result = self.db.insert_many(all_flights)
            logging.info(f"Successfully inserted {len(insert_result.inserted_ids)} documents into MongoDB.")

        except Exception as db_final_err:
            logging.error(f"CRITICAL ERROR during final database update: {db_final_err}", exc_info=True)

    def close_driver(self):
        """Closes the WebDriver."""
        if self.driver:
            self.driver.quit()
            logging.info("WebDriver closed.")


if __name__ == "__main__":
    DEPARTURE_AIRPORTS = ["HAN", "SGN"]
    # DEPARTURE_AIRPORTS = ["HAN"]

    ARRIVAL_AIRPORT = "DAD"
    TARGET_FLIGHT_COUNT_PER_RUN = 20 # Adjust as needed

    crawler = KayakFlightCrawler()
    # Get tomorrow and the day after
    tomorrow_str, day_after_tomorrow_str = crawler._get_dates()
    dates_to_scrape = [tomorrow_str, day_after_tomorrow_str]

    try:
        for departure in DEPARTURE_AIRPORTS:
            for date_str in dates_to_scrape:
                logging.info(f"""
{'='*30}
Starting scrape for: {departure} -> {ARRIVAL_AIRPORT} on {date_str}
{'='*30}
""")
                crawler.scrape_flights(departure, ARRIVAL_AIRPORT, date_str, target_count=TARGET_FLIGHT_COUNT_PER_RUN)
                time.sleep(5) # Add a small delay between requests

    except Exception as e:
        logging.critical(f"An error occurred in the main execution block: {e}", exc_info=True)
    finally:
        # --- Final Database Update --- 
        # Call the dedicated method to handle DB update
        crawler._update_database(crawler.all_scraped_flights)
        
        # --- Close Driver --- 
        crawler.close_driver()
        logging.info("Scraping process finished.")
