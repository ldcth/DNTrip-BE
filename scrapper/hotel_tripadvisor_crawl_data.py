import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException, WebDriverException
import time
import json
import re
import os
import logging
import random

# Import the base crawler
# from .hotel_tripadvisor import TripadvisorCrawler # REMOVED IMPORT

# Configure logging for this script
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# class HotelDetailCrawler(TripadvisorCrawler): # REMOVED INHERITANCE
class HotelDetailCrawler:
    """
    Crawls TripAdvisor hotel detail pages based on a list of URLs
    and saves the extracted information.
    """
    def __init__(self, input_url_file="tripadvisor_da_nang_hotel_urls.json", output_detail_file="tripadvisor_da_nang_hotel_details.json"):
        self.driver = None # Driver will be initialized in the loop
        self.detail_wait = None # Wait will be initialized in the loop

        # Set input/output files
        self.output_file = output_detail_file
        self.input_url_file = input_url_file
        self.hotels_data = [] 
        self.processed_urls = set() 

        logging.info("HotelDetailCrawler initialized (driver will start in loop).")

    def extract_rating_count(self, text):
        """Extracts the numerical rating count from text like '(1,234 reviews)'."""
        if not text:
            return "N/A"
        # Improved regex to handle various formats and potential lack of space
        match = re.search(r'([\d,]+)\s*review', text, re.IGNORECASE)
        if match:
            try:
                # Remove commas before converting to int
                return int(match.group(1).replace(',', ''))
            except ValueError:
                return "N/A" 
        return "N/A"


    def get_hotel_details(self, hotel_url):
        """Extracts info from a hotel detail page. Assumes driver is already running."""
        logging.info(f"Processing hotel detail page: {hotel_url}")
        # original_window = self.driver.current_window_handle # No longer needed with single window per URL
        hotel_info = {"name": "N/A", "price": "N/A", "rating": "N/A", "rating_count": "N/A", "address": "N/A", "description": "N/A", "url": hotel_url, "lat": None, "lon": None} # Add URL to output

        try:
            # Load URL directly into the current window
            self.driver.get(hotel_url)
            logging.info("Waiting after loading hotel detail page...")

            # --- Wait for and find the main container element --- 
            key_container_xpath = "//div[@class='IDaDx Iwmxp cyIij fluiI SMjpI']" # Main container for name, address, rating etc.
            try:
                key_container = self.detail_wait.until(EC.visibility_of_element_located((By.XPATH, key_container_xpath)))
                logging.info("Key container element found.")
                time.sleep(1) # REDUCED Short pause after finding container
            except TimeoutException:
                logging.error(f"Timeout waiting for key container ({key_container_xpath}) on {hotel_url}")
                return hotel_info # Return partially filled info

            # --- Extract Name (within key_container) ---
            try:
                # Use .// to search within the key_container element
                name_element = key_container.find_element(By.XPATH, "//div[id='HEADING']")
                hotel_info["name"] = name_element.text.strip()
                logging.info(f"Found name: {hotel_info['name']}")
                time.sleep(random.uniform(0.5, 1.0)) # REDUCED SLEEP
            except NoSuchElementException:
                logging.warning(f"Could not find name within key container for {hotel_url}")
                # Attempt fallback (still within key_container)
                try:
                    fallback_name = key_container.find_element(By.XPATH, ".//h1[contains(@class, 'biGQs')]") # Older class
                    hotel_info["name"] = fallback_name.text.strip()
                    logging.info(f"Found name (fallback): {hotel_info['name']}")
                    time.sleep(random.uniform(0.5, 1.0)) # REDUCED SLEEP
                except NoSuchElementException:
                    logging.warning("Fallback name lookup also failed within key container.")

            # --- Extract Rating & Rating Count (within key_container) ---
            try:
                 # Container for rating/reviews within the main key_container
                 # Using relative XPath from key_container
                 rating_review_container_xpath = ".//div[@class='irnhs f k']"
                 logging.warning(f"Looking for rating review container with xpath: {rating_review_container_xpath}")
                 rating_review_container = key_container.find_element(By.XPATH, rating_review_container_xpath)
                 logging.warning("Found rating_review_container.")
                 container_xpath = ".//div[@class='MyMKp u']"
                 logging.warning(f"Looking for rating container within review container with xpath: {container_xpath}")
                 rating_container = rating_review_container.find_element(By.XPATH, container_xpath)
                 logging.warning("Found rating_container.")

                 # Rating (within rating_container)
                 try:
                     rating_text_element = rating_container.find_element(By.XPATH, ".//div[@class='biGQs _P pZUbB KxBGd']")
                     rating_value = rating_text_element.text.strip()
                     if rating_value:
                         hotel_info["rating"] = rating_value + " bubbles"
                     logging.info(f"Found rating: {hotel_info['rating']}")
                     time.sleep(random.uniform(0.5, 1.0)) # REDUCED SLEEP
                 except NoSuchElementException:
                     logging.warning(f"Could not find rating text element within rating container for {hotel_url}")

                 # Rating Count (within rating_container)
                 try:
                     review_count_element_container = rating_container.find_element(By.XPATH, ".//div[@class='nKWJn u qMyjI']" )
                     review_count_element = review_count_element_container.find_element(By.XPATH, ".//div[@class='biGQs _P pZUbB KxBGd']" )
                     review_text = review_count_element.text.strip()
                     if review_text:
                         hotel_info["rating_count"] = self.extract_rating_count(review_text)
                     logging.info(f"Found rating count: {hotel_info['rating_count']}")
                     time.sleep(random.uniform(0.5, 1.0)) # REDUCED SLEEP
                 except NoSuchElementException:
                     logging.warning(f"Could not find review count element within rating container for {hotel_url}")

            except NoSuchElementException:
                 logging.warning(f"Could not find rating/review container within key container for {hotel_url}")

            # --- Extract Address (within key_container) ---
            try:
                # Search for address button/span within key_container
                container_xpath = "//div[@class='irnhs f k']"
                address_container = key_container.find_element(By.XPATH, container_xpath)
                address_container_1= address_container.find_element(By.XPATH, ".//div[@class='FhOgt H3 f u fRLPH']")
                address_element = address_container_1.find_element(By.XPATH, ".//span[@class='biGQs _P pZUbB KxBGd']")
                hotel_info["address"] = address_element.text.strip()
                logging.info(f"Found address: {hotel_info['address']}")
                time.sleep(random.uniform(0.5, 1.0)) # REDUCED SLEEP
            except NoSuchElementException:
                logging.warning(f"Could not find address element within key container for {hotel_url}")
           
            # --- Extract Price (Attempt within key_container, but known to be unreliable) ---

            try:
                 # Look for price block within the key_container
                container_xpath = "//div[@class='irnhs f k']"
                price_container = key_container.find_element(By.XPATH, container_xpath)
                price_container_1= price_container.find_element(By.XPATH, ".//div[@class='AVTFm']")
                price_element = price_container_1.find_element(By.XPATH, ".//div[@class='biGQs _P fiohW uuBRH']")
                hotel_info["price"] = price_element.text.strip()
                logging.info(f"Found price indication: {hotel_info['price']}")
                time.sleep(random.uniform(0.5, 1.0)) # REDUCED SLEEP
            except NoSuchElementException:
                 logging.info(f"Could not find price element within key container for {hotel_url} (this is common).")
            # --- Extract Description (Specific Path - Not within key_container) ---
            try:
                # 1. Find div.ythkR globally
                desc_container_1_xpath = "//div[@class='ythkR']"
                desc_container_1 = self.detail_wait.until(EC.visibility_of_element_located((By.XPATH, desc_container_1_xpath)))
                logging.debug("Found description container 1 (ythkR)")

                # 2. Inside that, find div.bizou._T.Z.BB.wjJkB
                desc_container_2_xpath = ".//div[@class='bizou _T Z BB wjJkB']"
                desc_container_2 = desc_container_1.find_element(By.XPATH, desc_container_2_xpath)
                logging.debug("Found description container 2 (bizou...)")

                # 3. Inside that, find div._T.FKffI.TPznB.Ci.ajMTa.Ps.Z.BB
                description_element_xpath = ".//div[@class='_T FKffI TPznB Ci ajMTa Ps Z BB']"
                description_element = desc_container_2.find_element(By.XPATH, description_element_xpath)

                hotel_info["description"] = description_element.text.strip()
                logging.info(f"Found description (partial): {hotel_info['description'][:100]}...")
                time.sleep(random.uniform(0.5, 1.0)) # REDUCED SLEEP

            except (NoSuchElementException, TimeoutException) as desc_err:
                logging.warning(f"Could not find description using specific path for {hotel_url}: {desc_err}")
                # Removed the old fallback logic as we are using the specific path now.


        # --- General Error Handling (Specific to this method) --- 
        except TimeoutException as e:
            # This catches timeouts during element finding within this method
            logging.error(f"TimeoutException during detail extraction for {hotel_url}: {e}")
            # Optionally save screenshot here if needed for debugging this specific failure
            # self.driver.save_screenshot(f"error_detail_extract_timeout_{hotel_info.get('name', 'unknown').replace(' ', '_')}.png")
        except WebDriverException as e:
             logging.error(f"WebDriverException during detail extraction for {hotel_url}: {e}")
        except Exception as e:
            logging.error(f"Unexpected error during detail extraction {hotel_url}: {e}", exc_info=True)
        # REMOVED Finally block for closing tab - driver is quit in crawl_details loop
        # finally:
            # logging.info(f"Closing tab for: {hotel_url}")
            # ... (tab closing/switching logic removed)

        # Return collected info
        return hotel_info


    def crawl_details(self):
        """Loads URLs and crawls details for each, restarting driver per URL."""
        logging.info(f"Starting hotel detail crawl. Input URLs: {self.input_url_file}, Output Details: {self.output_file}")

        # Load URLs to process
        try:
            with open(self.input_url_file, 'r', encoding='utf-8') as f:
                urls_to_crawl = json.load(f)
            logging.info(f"Loaded {len(urls_to_crawl)} URLs from {self.input_url_file}")
            if not isinstance(urls_to_crawl, list):
                logging.error("Input file does not contain a valid JSON list of URLs. Aborting.")
                return
        except FileNotFoundError:
            logging.error(f"Input URL file not found: {self.input_url_file}. Aborting.")
            return
        except (json.JSONDecodeError, IOError) as e:
            logging.error(f"Error reading or parsing input URL file {self.input_url_file}: {e}. Aborting.")
            return

        # Load existing data if output file exists to allow resuming
        if os.path.exists(self.output_file):
            logging.info(f"Output file {self.output_file} exists. Loading previous details.")
            try:
                with open(self.output_file, 'r', encoding='utf-8') as f:
                    self.hotels_data = json.load(f)
                    # Populate processed URLs set from loaded data
                    self.processed_urls = set(hotel.get('url') for hotel in self.hotels_data if hotel.get('url'))
                    logging.info(f"Loaded {len(self.hotels_data)} existing hotel details. {len(self.processed_urls)} URLs already processed.")
            except (json.JSONDecodeError, IOError) as e:
                 logging.error(f"Error loading existing detail file {self.output_file}: {e}. Starting fresh.")
                 self.hotels_data = []
                 self.processed_urls = set()
                 try:
                     with open(self.output_file, 'w') as f: json.dump([], f) # Create empty list file
                 except IOError as write_err:
                     logging.error(f"Could not create empty output file {self.output_file}: {write_err}")
        else:
            logging.info("No existing output file found. Starting fresh.")
            self.hotels_data = []
            self.processed_urls = set()
            try:
                 with open(self.output_file, 'w') as f: json.dump([], f) # Create empty list file
            except IOError as write_err:
                 logging.error(f"Could not create empty output file {self.output_file}: {write_err}")

        # --- Main Detail Crawling Loop ---        
        urls_processed_this_session = 0
        for i, url in enumerate(urls_to_crawl):
            logging.info(f"Processing URL {i+1}/{len(urls_to_crawl)}: {url}")

            if not url or not url.startswith("http"):
                logging.warning(f"Skipping invalid URL: {url}")
                continue

            base_url = url.split('?')[0] # Normalize URL slightly
            if base_url in self.processed_urls:
                logging.info(f"URL already processed: {base_url}. Skipping.")
                continue

            # --- Initialize driver for this specific URL --- 
            self.driver = None # Ensure driver is None before starting
            try:
                logging.info(f"Initializing driver for URL: {url}")
                opts = uc.ChromeOptions()
                opts.add_argument("--window-size=1920,1080")
                # Add other options if needed
                logging.info("PROXY DISABLED - Using direct connection.")
                self.driver = uc.Chrome(options=opts)
                time.sleep(2) # REDUCED Wait after driver starts
                self.detail_wait = WebDriverWait(self.driver, 25)
                logging.info("Driver initialized successfully for this URL.")

                # --- Get hotel details using the initialized driver ---
                hotel_details = self.get_hotel_details(url)

                # Add to data only if useful info was found
                if hotel_details and hotel_details.get("name") != "N/A":
                    self.hotels_data.append(hotel_details)
                    self.processed_urls.add(base_url)
                    urls_processed_this_session += 1
                    logging.info(f"Successfully processed: {hotel_details.get('name')}. Total details collected: {len(self.hotels_data)}")
                    self.save_results() # Save after each success
                else:
                    logging.warning(f"Failed to extract sufficient details for {url}. Skipping storage.")
            
            except WebDriverException as e: # Catch driver specific errors here
                logging.error(f"WebDriverException during setup or processing for {url}: {e}", exc_info=True)
                # Attempt to save screenshot if driver exists
                if self.driver:
                    try:
                        self.driver.save_screenshot(f"error_webdriver_exception_{i+1}.png")
                    except Exception as ss_err:
                         logging.error(f"Could not save screenshot after WebDriverException: {ss_err}")
            except Exception as loop_err:
                logging.error(f"Unexpected error processing URL {url} in main loop: {loop_err}", exc_info=True)

            finally:
                # --- Quit driver after processing this URL --- 
                if self.driver:
                    logging.info(f"Quitting driver for URL: {url}")
                    try:
                        self.driver.quit()
                    except Exception as quit_err:
                        logging.error(f"Error quitting driver: {quit_err}")
                    self.driver = None # Reset driver variable
                logging.info(f"Finished processing URL {i+1}. Pausing before next...")
                # Add a delay between processing each URL (after quitting driver)
                time.sleep(random.uniform(1.5, 3.0)) # REDUCED Shorter delay as driver restart takes time

        # --- End of Loop ---        
        logging.info(f"Finished processing all URLs. Processed {urls_processed_this_session} new URLs in this session.")
        # Final save is less critical now, but good practice
        self.save_results()
        # No driver quit needed here as it's done in the loop
        logging.info("--- Hotel Detail Scraper Finished ---")


    def save_results(self):
        """Saves the collected hotel details to a JSON file."""
        logging.info(f"Attempting to save {len(self.hotels_data)} hotel details to {self.output_file}...")
        try:
            with open(self.output_file, 'w', encoding='utf-8') as f:
                json.dump(self.hotels_data, f, ensure_ascii=False, indent=2)
            logging.info("Save complete.")
        except IOError as e:
            logging.error(f"Error saving data to {self.output_file}: {e}")
        except Exception as e:
            logging.error(f"An unexpected error occurred during saving: {e}")


if __name__ == "__main__":
    input_urls = "tripadvisor_da_nang_hotel_urls.json"
    output_details = "tripadvisor_da_nang_hotel_details.json"

    logging.info("--- Starting TripAdvisor Hotel Detail Scraper ---")
    detail_crawler = HotelDetailCrawler(input_url_file=input_urls, output_detail_file=output_details)
    detail_crawler.crawl_details()
    logging.info("--- Hotel Detail Scraper Finished ---")

    # Optional: Final check
    try:
        with open(output_details, 'r', encoding='utf-8') as f:
            final_data = json.load(f)
            logging.info(f"Final check: {len(final_data)} hotel details found in {output_details}")
    except Exception as e:
        logging.error(f"Error during final check of {output_details}: {e}")
