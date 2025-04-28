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

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class TripadvisorFullCrawler:
    """
    Combines TripAdvisor URL collection and hotel detail scraping into a single run,
    using separate driver sessions for URL collection and each detail extraction.
    """
    def __init__(self, output_detail_file="tripadvisor_da_nang_final_details.json", url_target_count=30,
                 url_output_file="scrapper/data/collected_hotel_urls.json",
                 collect_urls=True, extract_details=True):
        self.output_file = output_detail_file
        self.url_target_count = url_target_count
        self.url_output_file = url_output_file
        self.collect_urls = collect_urls
        self.extract_details = extract_details
        self.final_hotels_data = [] # Store final detailed results
        self.processed_urls_set = set() # Keep track of processed URLs if resuming/re-running

        # --- Driver related attributes initialized to None ---
        self.driver = None
        self.list_wait = None
        self.detail_wait = None
        # --- End Driver related attributes ---

        # Base URL for the initial page (no -oa0)
        # self.base_url = "https://www.tripadvisor.com/Hotels-g298085-a_travelersChoice.1-Da_Nang-Hotels.html#SPLITVIEWLIST"
        self.base_url = "https://www.tripadvisor.com/Hotels-g298085-a_travelersChoice.1-Da_Nang-Hotels.html"
        # Template for subsequent pages (with -oa{offset})
        # self.base_url_template = "https://www.tripadvisor.com/Hotels-g298085-oa{offset}-a_travelersChoice.1-Da_Nang-Hotels.html#SPLITVIEWLIST"
        self.base_url_template = "https://www.tripadvisor.com/Hotels-g298085-oa{offset}-a_travelersChoice.1-Da_Nang-Hotels.html"

    # --- Driver Initialization Helper ---
    def _initialize_driver(self):
        """Initializes a new undetected-chromedriver instance and waits."""
        if self.driver: # Quit existing driver if any
             try:
                 self.driver.quit()
             except Exception as e:
                 logging.warning(f"Exception while quitting previous driver: {e}")
             self.driver = None

        logging.info("Initializing new undetected-chromedriver instance...")
        opts = uc.ChromeOptions()
        opts.add_argument("--window-size=1920,1080")
        # opts.add_argument('--disable-blink-features=AutomationControlled') # Optional anti-detection
        # opts.add_argument('--ignore-certificate-errors') # Optional
        # proxy_server = "127.0.0.1:9050" # Tor SOCKS5 default port
        # opts.add_argument(f'--proxy-server=socks5://{proxy_server}')
        # logging.info(f"Using SOCKS5 proxy server: {proxy_server}")

        try:
            self.driver = uc.Chrome(options=opts)
            logging.info("Waiting a few seconds after driver initialization...")
            time.sleep(random.uniform(1.5, 3.0)) # Reduced wait
            logging.info("Driver initialized.")
            # Initialize waits associated with this driver instance
            self.list_wait = WebDriverWait(self.driver, 20)
            self.detail_wait = WebDriverWait(self.driver, 25)
            return True
        except Exception as e:
            logging.error(f"Failed to initialize Chrome driver: {e}", exc_info=True)
            self.driver = None # Ensure driver is None on failure
            return False

    # --- Driver Quitting Helper ---
    def _quit_driver(self):
        """Quits the current driver instance if it exists."""
        if self.driver:
            logging.info("Quitting current WebDriver instance...")
            try:
                self.driver.quit()
                logging.info("WebDriver quit successfully.")
            except Exception as e:
                logging.error(f"Error quitting WebDriver: {e}", exc_info=True)
            finally:
                 self.driver = None # Reset driver attributes
                 self.list_wait = None
                 self.detail_wait = None

    # --- Helper Methods ---
    def extract_rating_count(self, text):
        """Extracts the numerical rating count from text like '(1,234 reviews)'."""
        if not text:
            return "N/A"
        match = re.search(r'([\d,]+)\s*review', text, re.IGNORECASE)
        if match:
            try:
                return int(match.group(1).replace(',', ''))
            except ValueError:
                return "N/A"
        return "N/A"
    
    # --- Phase 1: URL Collection Methods ---
    # def select_checkin_checkout_dates(self):
    #     """Performs a specific button click sequence potentially related to date/filters."""
    #     logging.info("Attempting specific button click sequence...")
    #     try:
    #         time.sleep(random.uniform(1.0, 2.0)) # Reduced delay
    #         # 1. Find the outer container div
    #         outer_container_selector = "//div[@class='SKCqA _T R2 f e qhZKQ']"
    #         outer_container = self.list_wait.until(EC.visibility_of_element_located((By.XPATH, outer_container_selector)))
    #         logging.info("Outer container found.")

    #         # 2. Find the inner div
    #         inner_container_selector = ".//div[@class='oljCt Pj PN Pw PA Z BB']"
    #         inner_container = outer_container.find_element(By.XPATH, inner_container_selector)
    #         logging.info("Inner container found.")

    #         # 3. Find all buttons matching the class
    #         button_selector = ".//button[@class='rmyCe _G B- z _S c Wc wSSLS jWkoZ QHaGY']"
    #         buttons = inner_container.find_elements(By.XPATH, button_selector)
    #         logging.info(f"Found {len(buttons)} matching buttons.")

    #         # 4. Click the second button (index 1) if present
    #         if len(buttons) >= 2:
    #             next_week_button = buttons[1]
    #             logging.info("Attempting to click the next week button...")
    #             try:
    #                 self.driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", next_week_button)
    #                 time.sleep(random.uniform(0.5, 1.0)) # Reduced delay
    #                 self.driver.execute_script("arguments[0].click();", next_week_button)
    #                 logging.info("Clicked the next week button via JavaScript.")
    #                 time.sleep(random.uniform(2.0, 3.5)) # Reduced wait

    #                 # --- Click the final 'Update' button ---
    #                 logging.info("Starting sequence to click final 'Update' button...")
    #                 try:
    #                     final_container_1_selector = "//div[@class='PeChA IPdZD GTGpm']"
    #                     final_container_1 = self.list_wait.until(EC.visibility_of_element_located((By.XPATH, final_container_1_selector)))
    #                     logging.info("Found final container 1 (PeChA...).")

    #                     final_container_2_selector = ".//div[@class='EcOjx']"
    #                     final_container_2 = final_container_1.find_element(By.XPATH, final_container_2_selector)
    #                     logging.info("Found final container 2 (EcOjx).")

    #                     final_button_selector = ".//button[@class='BrOJk u j z _F wSSLS tIqAi iNBVo']" # This is likely the 'Update' or 'Apply' button
    #                     final_button = self.list_wait.until(EC.element_to_be_clickable((By.XPATH, final_container_2_selector + final_button_selector[1:])))
    #                     logging.info("Found final button. Clicking...")
    #                     final_button.click()
    #                     logging.info("Clicked final button.")
    #                     time.sleep(random.uniform(1.0, 2.0)) # Reduced pause

    #                 except (NoSuchElementException, TimeoutException) as final_err:
    #                     logging.error(f"Error during final button click sequence: {final_err}")
    #                     self.driver.save_screenshot("error_final_button_sequence.png")
    #             except Exception as click_err:
    #                  logging.error(f"Failed to click the second button even with JavaScript: {click_err}")
    #                  self.driver.save_screenshot("error_js_click_failed.png")
    #         else:
    #             logging.warning(f"Could not find the second button matching the selector. Found {len(buttons)} buttons.")
    #             self.driver.save_screenshot("error_button_not_found.png")

    #         logging.info("Button click sequence complete.")

    #     except (NoSuchElementException, TimeoutException) as e:
    #         logging.error(f"Error during button click sequence: {e}")
    #         self.driver.save_screenshot("error_button_sequence.png")
    #     except Exception as e:
    #         logging.error(f"An unexpected error occurred during button click sequence: {e}", exc_info=True)
    #         self.driver.save_screenshot("error_button_sequence_unexpected.png")


    # def crawl_hotel_urls(self):
    #     """Crawls TripAdvisor list pages to collect hotel detail URLs."""
    #     collected_urls = []
    #     collected_urls_set = set() # Track URLs collected in this specific run
    #     offset = 0
    #     max_hotels_per_page = 30

    #     try:
    #         # --- Load initial page (offset 0) and select dates ---
    #         logging.info(f"Loading initial page for URL collection: {self.base_url}")
    #         self.driver.get(self.base_url)
    #         time.sleep(random.uniform(2.0, 3.5)) # Reduced wait
    #         logging.info("Initial page loaded, proceeding to button sequence.")

    #         self.select_checkin_checkout_dates() # Perform button click sequence
    #         logging.info("Button sequence finished, starting URL collection loop.")

    #         # --- Main URL Collection Loop ---
    #         while len(collected_urls) < self.url_target_count:
    #             # Determine the correct URL for the current offset
    #             if offset == 0:
    #                 # Already on the page after button clicks, or reload if needed
    #                 current_url = self.driver.current_url
    #                 if "SPLITVIEWLIST" not in current_url: # Check if we navigated away unexpectedly
    #                      logging.warning("Not on expected list view URL after button clicks, reloading base URL.")
    #                      self.driver.get(self.base_url)
    #                      time.sleep(random.uniform(2.5, 4.0)) # Reduced wait
    #                 expected_url = self.driver.current_url # Use the actual current URL for offset 0
    #                 logging.info(f"Processing page offset 0: {expected_url}")
    #             else:
    #                 expected_url = self.base_url_template.format(offset=offset)
    #                 logging.info(f"Processing page offset {offset}: {expected_url}")
    #                 # Navigate to the next page URL
    #                 if self.driver.current_url != expected_url:
    #                     logging.info(f"Navigating to offset {offset}...")
    #                     self.driver.get(expected_url)
    #                     time.sleep(random.uniform(2.0, 4.0)) # Reduced wait
    #                     logging.info(f"Navigation to {expected_url} complete.")
                        
    #                     # --- ADD: Re-apply date selection and refresh for offset pages ---
    #                     logging.info(f"Re-applying date selection for offset {offset}...")
    #                     self.select_checkin_checkout_dates()
    #                     logging.info(f"Refreshing page after date selection for offset {offset}...")
    #                     self.driver.refresh()
    #                     time.sleep(random.uniform(3.0, 5.0)) # Wait for page refresh
    #                     logging.info("Page refreshed.")
    #                     # --- END ADD ---

    #             page_url = self.driver.current_url
    #             logging.info(f"Now collecting URLs from page: {page_url} (Target: {self.url_target_count}, Current URLs: {len(collected_urls)})")

    #             try:
    #                 # Wait for the main hotel list container
    #                 hotel_list_container_selector = "//div[contains(@class, 'oobXg')]"
    #                 self.list_wait.until(EC.visibility_of_element_located((By.XPATH, hotel_list_container_selector)))
    #                 list_container = self.driver.find_element(By.XPATH, hotel_list_container_selector)

    #                 # Find hotel 'li' elements
    #                 hotel_elements_selector = ".//li[contains(@class, 'cauVP')]"
    #                 hotel_list_items = list_container.find_elements(By.XPATH, hotel_elements_selector)
    #                 logging.info(f"Found {len(hotel_list_items)} potential hotel items on page.")

    #                 if not hotel_list_items:
    #                     logging.warning("No hotel list items found using primary selector. Trying broader 'li' tag search...")
    #                     hotel_list_items = list_container.find_elements(By.TAG_NAME, 'li')
    #                     logging.info(f"Found {len(hotel_list_items)} items using broader 'li' tag search.")
    #                     if not hotel_list_items:
    #                        logging.error("Still no hotel items found. Ending URL collection.")
    #                        break # Exit URL collection loop

    #                 collected_on_page = 0
    #                 for i, item in enumerate(hotel_list_items):
    #                     # Find the primary link to the hotel details page
    #                     hotel_link_selector = ".//a[@class='BMQDV _F Gv wSSLS SwZTJ w']"
    #                     try:
    #                         hotel_link_element = item.find_element(By.XPATH, hotel_link_selector)
    #                         hotel_url = hotel_link_element.get_attribute('href')

    #                         if hotel_url:
    #                             # Strip query parameters
    #                             stripped_url = hotel_url.split('?')[0]
    #                             if stripped_url not in collected_urls_set:
    #                                 logging.info(f"Found new unique hotel URL: {stripped_url} (Original: {hotel_url})")
    #                                 collected_urls.append(stripped_url) # Store stripped URL
    #                                 collected_urls_set.add(stripped_url)
    #                                 # --- Call incremental save --- 
    #                                 self._append_url_to_file(stripped_url)
    #                                 # --- End Call ---
    #                                 collected_on_page += 1
    #                                 if len(collected_urls) >= self.url_target_count:
    #                                     logging.info(f"Reached target URL count of {self.url_target_count}.")
    #                                     break # Exit item loop
    #                             else:
    #                                 logging.debug(f"Already collected URL: {stripped_url}. Skipping.")
    #                         else:
    #                             logging.warning("Found link element but no href attribute.")

    #                     except NoSuchElementException:
    #                         logging.debug(f"Could not find primary hotel link ({hotel_link_selector}) in list item {i+1}.")
    #                     except Exception as item_err:
    #                          logging.warning(f"Error processing list item {i+1}: {item_err}")
                        
    #                     # --- ADDED: Short delay after processing each item ---
    #                     time.sleep(random.uniform(0.2, 0.4)) # Short pause between item checks
    #                     # --- END ADDED ---

    #                 # Check if target count is reached after processing the page
    #                 if len(collected_urls) >= self.url_target_count:
    #                     break # Exit outer loop

    #                 logging.info(f"Finished processing items on page {page_url}. Found {collected_on_page} new URLs. Pausing...")
    #                 time.sleep(random.uniform(1.0, 2.0)) # Reduced pause

    #                 # --- Restart driver before moving to the next page --- 
    #                 if len(collected_urls) < self.url_target_count: # Only restart if we need more URLs
    #                     logging.info(f"Preparing to navigate to next page (offset {offset + max_hotels_per_page}). Restarting driver...")
    #                     self._quit_driver()
    #                     if not self._initialize_driver():
    #                          logging.error("Failed to re-initialize driver for next page. Stopping URL collection.")
    #                          break # Exit outer loop if driver restart fails
    #                     logging.info("Driver restarted successfully.")
    #                 # --- End driver restart --- 

    #                 # Move to the next page
    #                 if len(hotel_list_items) > 0:
    #                     offset += max_hotels_per_page
    #                 else:
    #                      logging.warning(f"No hotel list items found on page with offset {offset}. Stopping pagination.")
    #                      break # Stop if a page yielded no list items

    #             except (TimeoutException, NoSuchElementException) as e:
    #                 logging.error(f"Could not find hotel list container or critical element on page {page_url}: {e}")
    #                 self.driver.save_screenshot(f"error_list_page_{offset}.png")
    #                 break # Stop URL collection
    #             except Exception as e:
    #                  logging.error(f"An unexpected error occurred processing page {page_url}: {e}", exc_info=True)
    #                  self.driver.save_screenshot(f"error_list_page_unexpected_{offset}.png")
    #                  break # Stop on unexpected errors

    #         logging.info(f"URL collection phase finished. Collected {len(collected_urls)} unique URLs.")
    #         return collected_urls

    #     except WebDriverException as e:
    #          logging.critical(f"A WebDriverException occurred during the URL collection phase: {e}", exc_info=True)
    #          if self.driver: self.driver.save_screenshot("critical_url_collection_webdriver_error.png")
    #          return collected_urls # Return whatever was collected before the error
    #     except Exception as e:
    #         logging.critical(f"A critical error occurred during URL collection phase: {e}", exc_info=True)
    #         if self.driver: self.driver.save_screenshot("critical_url_collection_error.png")
    #         return collected_urls # Return potentially partial list

    # --- Phase 1: URL Collection Methods (second base URL) ---
    def select_outside_date(self):
        """Performs a specific button click outside of the date selection."""
        logging.info("Attempting specific outside date button click sequence...")
        try:
            time.sleep(random.uniform(1.0, 2.0)) # Reduced delay
            h1_element = "//h1[@class='biGQs _P fiohW avBIb KagYY']"
            h1_element = self.list_wait.until(EC.visibility_of_element_located((By.XPATH, h1_element)))
            logging.info("h1 element found.")
            h1_element.click()
            logging.info("h1 element clicked.")

        except (NoSuchElementException, TimeoutException) as e:
            logging.error(f"Error during outside date button click sequence: {e}")
            self.driver.save_screenshot("error_outside_date_button_sequence.png")
        except Exception as e:
            logging.error(f"An unexpected error occurred during outside date button click sequence: {e}", exc_info=True)
            self.driver.save_screenshot("error_outside_date_button_sequence_unexpected.png")


    def crawl_hotel_urls(self):
        """Crawls TripAdvisor list pages to collect hotel detail URLs."""
        collected_urls = []
        collected_urls_set = set() # Track URLs collected in this specific run
        offset = 0
        max_hotels_per_page = 30

        try:
            # --- Load initial page (offset 0) and select dates ---
            logging.info(f"Loading initial page for URL collection: {self.base_url}")
            self.driver.get(self.base_url)
            time.sleep(random.uniform(2.0, 3.5)) # Reduced wait
            logging.info("Initial page loaded, proceeding to outside date button sequence.")

            self.select_outside_date() # Perform button click sequence
            logging.info("Outside date button sequence finished, starting URL collection loop.")

            # --- Main URL Collection Loop ---
            while len(collected_urls) < self.url_target_count:
                # Determine the correct URL for the current offset
                if offset == 0:
                    # Already on the page after button clicks, or reload if needed
                    current_url = self.driver.current_url
                else:
                    expected_url = self.base_url_template.format(offset=offset)
                    logging.info(f"Processing page offset {offset}: {expected_url}")
                    # Navigate to the next page URL
                    if self.driver.current_url != expected_url:
                        logging.info(f"Navigating to offset {offset}...")
                        self.driver.get(expected_url)
                        time.sleep(random.uniform(2.0, 4.0)) # Reduced wait
                        logging.info(f"Navigation to {expected_url} complete.")
                        
                        # --- ADD: Re-apply date selection and refresh for offset pages ---
                        logging.info(f"Re-applying outside date selection for offset {offset}...")
                        self.select_outside_date()
                        logging.info(f"Refreshing page after outside date selection for offset {offset}...")
                        self.driver.refresh()
                        time.sleep(random.uniform(3.0, 5.0)) # Wait for page refresh
                        logging.info("Page refreshed.")
                        # --- END ADD ---

                page_url = self.driver.current_url
                logging.info(f"Now collecting URLs from page: {page_url} (Target: {self.url_target_count}, Current URLs: {len(collected_urls)})")

                try:
                    # Wait for the main hotel list container
                    hotel_list_container_selector = "//ol[@class='tAknw f e']"
                    self.list_wait.until(EC.visibility_of_element_located((By.XPATH, hotel_list_container_selector)))
                    list_container = self.driver.find_element(By.XPATH, hotel_list_container_selector)

                    # Find hotel 'li' elements
                    hotel_elements_selector = ".//li"
                    hotel_list_items = list_container.find_elements(By.XPATH, hotel_elements_selector)
                    logging.info(f"Found {len(hotel_list_items)} potential hotel items on page.")

                    if not hotel_list_items:
                        logging.warning("No hotel list items found using primary selector. Trying broader 'li' tag search...")
                        hotel_list_items = list_container.find_elements(By.TAG_NAME, 'li')
                        logging.info(f"Found {len(hotel_list_items)} items using broader 'li' tag search.")
                        if not hotel_list_items:
                           logging.error("Still no hotel items found. Ending URL collection.")
                           break # Exit URL collection loop

                    collected_on_page = 0
                    for i, item in enumerate(hotel_list_items):
                        # Find the primary link to the hotel details page
                        hotel_link_selector = ".//a[@class='BMQDV _F Gv wSSLS SwZTJ FGwzt ukgoS']"
                        try:
                            hotel_link_element = item.find_element(By.XPATH, hotel_link_selector)
                            hotel_url = hotel_link_element.get_attribute('href')

                            if hotel_url:
                                # Strip query parameters
                                stripped_url = hotel_url.split('?')[0]
                                if stripped_url not in collected_urls_set:
                                    logging.info(f"Found new unique hotel URL: {stripped_url} (Original: {hotel_url})")
                                    collected_urls.append(stripped_url) # Store stripped URL
                                    collected_urls_set.add(stripped_url)
                                    # --- Call incremental save --- 
                                    self._append_url_to_file(stripped_url)
                                    # --- End Call ---
                                    collected_on_page += 1
                                    if len(collected_urls) >= self.url_target_count:
                                        logging.info(f"Reached target URL count of {self.url_target_count}.")
                                        break # Exit item loop
                                else:
                                    logging.debug(f"Already collected URL: {stripped_url}. Skipping.")
                            else:
                                logging.warning("Found link element but no href attribute.")

                        except NoSuchElementException:
                            logging.debug(f"Could not find primary hotel link ({hotel_link_selector}) in list item {i+1}.")
                        except Exception as item_err:
                             logging.warning(f"Error processing list item {i+1}: {item_err}")
                        
                        # --- ADDED: Short delay after processing each item ---
                        time.sleep(random.uniform(0.2, 0.4)) # Short pause between item checks
                        # --- END ADDED ---

                    # Check if target count is reached after processing the page
                    if len(collected_urls) >= self.url_target_count:
                        break # Exit outer loop

                    logging.info(f"Finished processing items on page {page_url}. Found {collected_on_page} new URLs. Pausing...")
                    time.sleep(random.uniform(1.0, 2.0)) # Reduced pause

                    # --- Restart driver before moving to the next page --- 
                    if len(collected_urls) < self.url_target_count: # Only restart if we need more URLs
                        logging.info(f"Preparing to navigate to next page (offset {offset + max_hotels_per_page}). Restarting driver...")
                        self._quit_driver()
                        if not self._initialize_driver():
                             logging.error("Failed to re-initialize driver for next page. Stopping URL collection.")
                             break # Exit outer loop if driver restart fails
                        logging.info("Driver restarted successfully.")
                    # --- End driver restart --- 

                    # Move to the next page
                    if len(hotel_list_items) > 0:
                        offset += max_hotels_per_page
                    else:
                         logging.warning(f"No hotel list items found on page with offset {offset}. Stopping pagination.")
                         break # Stop if a page yielded no list items

                except (TimeoutException, NoSuchElementException) as e:
                    logging.error(f"Could not find hotel list container or critical element on page {page_url}: {e}")
                    self.driver.save_screenshot(f"error_list_page_{offset}.png")
                    break # Stop URL collection
                except Exception as e:
                     logging.error(f"An unexpected error occurred processing page {page_url}: {e}", exc_info=True)
                     self.driver.save_screenshot(f"error_list_page_unexpected_{offset}.png")
                     break # Stop on unexpected errors

            logging.info(f"URL collection phase finished. Collected {len(collected_urls)} unique URLs.")
            return collected_urls

        except WebDriverException as e:
             logging.critical(f"A WebDriverException occurred during the URL collection phase: {e}", exc_info=True)
             if self.driver: self.driver.save_screenshot("critical_url_collection_webdriver_error.png")
             return collected_urls # Return whatever was collected before the error
        except Exception as e:
            logging.critical(f"A critical error occurred during URL collection phase: {e}", exc_info=True)
            if self.driver: self.driver.save_screenshot("critical_url_collection_error.png")
            return collected_urls # Return potentially partial list
        
    # --- Phase 2: Detail Extraction Method ---
    def get_hotel_details(self, hotel_url):
        """
        Extracts info from a hotel detail page.
        Assumes self.driver and self.detail_wait are initialized BEFORE this call.
        """
        # --- Safety Check: Ensure driver exists before proceeding ---
        if not self.driver or not self.detail_wait:
             logging.error(f"Driver or Wait not initialized before calling get_hotel_details for {hotel_url}. Aborting detail extraction for this URL.")
             # Return structure indicating failure, but don't halt entirely
             return {"name": "N/A", "price": "N/A", "rating": "N/A", "rating_count": "N/A", "address": "N/A", "description": "N/A", "url": hotel_url, "error": "Driver not initialized"}

        logging.info(f"Processing hotel detail page: {hotel_url}")
        hotel_info = {"name": "N/A", "price": "N/A", "rating": "N/A", "rating_count": "N/A", "address": "N/A", "description": "N/A", "url": hotel_url, "lat": None, "lon": None}

        try:
            # Navigate to the hotel detail URL in the current window
            self.driver.get(hotel_url)
            logging.info("Waiting after loading hotel detail page...")
            # Give page time to load dynamic content
            time.sleep(random.uniform(1.5, 2.5)) # Reduced wait

            # --- Wait for and find the main container element ---
            key_container_xpath = "//div[@class='IDaDx Iwmxp cyIij fluiI SMjpI']"
            try:
                key_container = self.detail_wait.until(EC.visibility_of_element_located((By.XPATH, key_container_xpath)))
                logging.info("Key container element found.")
                time.sleep(0.5) # Short pause after finding container
            except TimeoutException:
                logging.error(f"Timeout waiting for key container ({key_container_xpath}) on {hotel_url}")
                self.driver.save_screenshot(f"error_detail_key_container_timeout_{time.time()}.png")
                return hotel_info # Return partially filled info

            # --- Extract Name (within key_container) ---
            try:
                # Use .// to search within the key_container element
                name_element = key_container.find_element(By.XPATH, ".//div[@id='HEADING']") # More specific ID if available
                hotel_info["name"] = name_element.text.strip()
                logging.info(f"Found name: {hotel_info['name']}")
            except NoSuchElementException:
                 logging.warning(f"Could not find name by ID 'HEADING' for {hotel_url}, trying H1 tag...")
                 try:
                      # Fallback using H1 tag within the container
                      name_element_h1 = key_container.find_element(By.XPATH, ".//h1")
                      hotel_info["name"] = name_element_h1.text.strip()
                      logging.info(f"Found name (fallback H1): {hotel_info['name']}")
                 except NoSuchElementException:
                      logging.error(f"Could not find name within key container using ID or H1 for {hotel_url}")


            # --- Extract Rating & Rating Count (within key_container) ---
            try:
                 # Container for rating/reviews within the main key_container
                 rating_review_container_xpath = ".//div[@class='irnhs f k']" # This class seems common near rating/address
                 rating_review_container = key_container.find_element(By.XPATH, rating_review_container_xpath)

                 # Rating Value (Bubbles) - Often represented numerically now
                 try:
                     # Look for the div containing the numeric rating like "4.5"
                     rating_value_div_xpath = ".//div[@class='MyMKp u']//div[contains(@class,'biGQs _P pZUbB KxBGd')]"
                     rating_value_element = rating_review_container.find_element(By.XPATH, rating_value_div_xpath)
                     rating_value = rating_value_element.text.strip()
                     if rating_value:
                         hotel_info["rating"] = f"{rating_value}" # Append unit for clarity
                     logging.info(f"Found rating value: {hotel_info['rating']}")
                 except NoSuchElementException:
                     logging.warning(f"Could not find rating value element for {hotel_url}")

                 # Rating Count (Reviews)
                 try:
                     # Look for the div containing the review count text like "1,234 reviews"
                     review_count_div_xpath = ".//div[@class='nKWJn u qMyjI']//div[contains(@class, 'biGQs _P pZUbB KxBGd')]"
                     review_count_element = rating_review_container.find_element(By.XPATH, review_count_div_xpath)
                     review_text = review_count_element.text.strip()
                     if review_text:
                         hotel_info["rating_count"] = self.extract_rating_count(review_text)
                     logging.info(f"Found rating count: {hotel_info['rating_count']}")
                 except NoSuchElementException:
                     logging.warning(f"Could not find review count element for {hotel_url}")

            except NoSuchElementException:
                 logging.warning(f"Could not find main rating/review container ('{rating_review_container_xpath}') within key container for {hotel_url}")


            # --- Extract Address (within key_container) ---
            try:
                # Search for address span within the specific sub-container
                address_container_xpath = ".//div[@class='FhOgt H3 f u fRLPH']//span[contains(@class,'biGQs _P pZUbB KxBGd')]"
                address_element = key_container.find_element(By.XPATH, address_container_xpath)
                hotel_info["address"] = address_element.text.strip()
                logging.info(f"Found address: {hotel_info['address']}")
            except NoSuchElementException:
                logging.warning(f"Could not find address element using primary path for {hotel_url}")
                # Add more specific fallbacks if needed, based on inspection

            # --- Extract Price (Often unreliable, attempt within key_container) ---
            try:
                # Look for a price indication element
                container_xpath = "//div[@class='irnhs f k']"
                price_container = key_container.find_element(By.XPATH, container_xpath)
                price_container_1= price_container.find_element(By.XPATH, ".//div[@class='AVTFm']")
                try:
                    price_element = price_container_1.find_element(By.XPATH, ".//div[@class='biGQs _P fiohW uuBRH']")
                    hotel_info["price"] = price_element.text.strip()
                    logging.info(f"Found price indication: {hotel_info['price']}")
                except NoSuchElementException:
                    logging.warning(f"Could not find price element within key container for {hotel_url} (this is common).")
                    try:
                        price_element = price_container_1.find_element(By.XPATH, ".//span[@class='biGQs _P ttuOS']")
                        if (price_element.text.strip().lower() == "check availability"):
                            price_list_container = self.detail_wait.until(EC.visibility_of_element_located((By.XPATH, '//div[@class="ythkR"]')))
                            price_list_container_1 = price_list_container.find_element(By.XPATH, ".//div[@class='VRono Gi B1 Z BB Pk PY Px PK']")
                            price_list_container_2 = price_list_container_1.find_element(By.XPATH, ".//div[@class='NalGx']")
                            price_list_container_3 = price_list_container_2.find_element(By.XPATH, ".//div[@class='pVXGZ']")
                            price_list_element = price_list_container_3.find_element(By.XPATH, ".//div[@class='TSGVz f']")
                            hotel_info["price"] = price_list_element.text.strip()
                            logging.info(f"Found price in LIST indication: {hotel_info['price']}")
                    except NoSuchElementException:
                        logging.warning(f"Could not find price element within list for {hotel_url} (this is common).")
            except NoSuchElementException:
                 logging.info(f"Could not find specific price element within key container for {hotel_url} (common).")

            # --- Extract Description (Specific Path - Outside key_container) ---
            try:
                # Follow the nested structure identified previously
                desc_container_1_xpath = "//div[@class='ythkR']"
                desc_container_1 = self.detail_wait.until(EC.visibility_of_element_located((By.XPATH, desc_container_1_xpath)))

                desc_container_2_xpath = ".//div[@class='bizou _T Z BB wjJkB']"
                desc_container_2 = desc_container_1.find_element(By.XPATH, desc_container_2_xpath)
                try:
                    description_element_xpath = ".//div[@class='_T FKffI TPznB Ci ajMTa Ps Z BB']"
                    description_element = desc_container_2.find_element(By.XPATH, description_element_xpath)
                    logging.info("Found description element.")
                except NoSuchElementException:
                    logging.warning(f"Could not find description element using specific path for {hotel_url}")
                    try:
                        description_element_xpath = ".//div[@class='_T FKffI TPznB Ci ajMTa Ps Z BB bmUTE']"
                        description_element = desc_container_2.find_element(By.XPATH, description_element_xpath)
                        logging.info("Found description element.")
                    except NoSuchElementException:
                        logging.warning(f"Could not find description element using specific path for {hotel_url}")

                hotel_info["description"] = description_element.text.strip()
                logging.info(f"Found description (partial): {hotel_info['description'][:100]}...")

            except (NoSuchElementException, TimeoutException) as desc_err:
                logging.warning(f"Could not find description using specific path for {hotel_url}: {desc_err}")


        # --- General Error Handling for this Method ---
        except TimeoutException as e:
            logging.error(f"TimeoutException during detail extraction for {hotel_url}: {e}")
            # Save screenshot on timeout within detail extraction
            try:
                if self.driver: self.driver.save_screenshot(f"error_detail_extract_timeout_{time.time()}.png")
            except Exception as ss_err:
                 logging.error(f"Could not save screenshot after detail TimeoutException: {ss_err}")
        except WebDriverException as e:
             logging.error(f"WebDriverException during detail extraction for {hotel_url}: {e}", exc_info=True)
             try:
                 if self.driver: self.driver.save_screenshot(f"error_detail_webdriver_exception_{time.time()}.png")
             except Exception as ss_err:
                  logging.error(f"Could not save screenshot after detail WebDriverException: {ss_err}")
        except Exception as e:
            logging.error(f"Unexpected error during detail extraction {hotel_url}: {e}", exc_info=True)
            try:
                if self.driver: self.driver.save_screenshot(f"error_detail_unexpected_{time.time()}.png")
            except Exception as ss_err:
                 logging.error(f"Could not save screenshot after detail unexpected error: {ss_err}")

        # --- NOTE: Driver is NOT quit here. It's quit in the run_full_crawl loop ---
        return hotel_info

    # --- Orchestration & Saving ---
    def load_existing_results(self):
        """Loads existing results from the output file if it exists."""
        if os.path.exists(self.output_file):
            logging.info(f"Output file {self.output_file} exists. Loading previous details.")
            try:
                with open(self.output_file, 'r', encoding='utf-8') as f:
                    self.final_hotels_data = json.load(f)
                    # Populate processed URLs set from loaded data
                    self.processed_urls_set = set(hotel.get('url') for hotel in self.final_hotels_data if hotel.get('url'))
                    logging.info(f"Loaded {len(self.final_hotels_data)} existing hotel details. {len(self.processed_urls_set)} URLs previously processed.")
            except (json.JSONDecodeError, IOError) as e:
                 logging.error(f"Error loading existing detail file {self.output_file}: {e}. Starting fresh list.")
                 self.final_hotels_data = []
                 self.processed_urls_set = set()
                 # Optionally back up corrupted file before overwriting
                 # os.rename(self.output_file, self.output_file + ".corrupted")
        else:
            logging.info("No existing output file found. Starting fresh detail list.")
            self.final_hotels_data = []
            self.processed_urls_set = set()


    def run_full_crawl(self):
        """Orchestrates the full crawl based on control flags."""
        start_time = time.time()
        logging.info("--- Starting Full TripAdvisor Crawl ---")
        self.driver = None # Ensure driver starts as None
        hotel_urls_to_process = [] # Initialize empty list

        try:
            # --- Phase 1: Collect URLs (Conditional) ---
            if self.collect_urls:
                logging.info("--- Starting Phase 1: URL Collection (Enabled) ---")

                # --- ADD: Ensure URL output file exists as empty list if starting fresh --- 
                if not os.path.exists(self.url_output_file) or os.path.getsize(self.url_output_file) == 0:
                    logging.info(f"Initializing URL output file: {self.url_output_file}")
                    try:
                        os.makedirs(os.path.dirname(self.url_output_file) or '.', exist_ok=True)
                        with open(self.url_output_file, 'w', encoding='utf-8') as f:
                            json.dump([], f)
                    except IOError as e:
                         logging.error(f"Could not initialize URL output file {self.url_output_file}: {e}")
                         # Decide whether to abort or continue without saving URLs
                         # return # Option: Abort if file cannot be initialized
                # --- END ADD ---

                # Initialize driver FOR URL Collection Phase
                if not self._initialize_driver():
                    logging.critical("Failed to initialize driver for URL Collection Phase. Aborting crawl.")

                collected_urls = self.crawl_hotel_urls() # This manages its own driver session
                logging.info("--- Finished Phase 1: URL Collection ---")

                # Save collected URLs if successful
                if collected_urls:
                    self._save_url_list(collected_urls)
                    hotel_urls_to_process = collected_urls # Use collected URLs for Phase 2
                else:
                    logging.warning("URL Collection phase ran but did not return any URLs.")
            
            elif self.extract_details: # If only extracting details, load URLs
                 logging.info("--- Skipping Phase 1: URL Collection (Disabled) ---")
                 return # Exit if both phases are disabled

            # --- Phase 2: Extract Details (Conditional) ---
            if self.extract_details:
                if not hotel_urls_to_process:
                    logging.warning("No URLs available to process for detail extraction. Skipping Phase 2.")
                else:
                    logging.info(f"--- Starting Phase 2: Detail extraction (Enabled) for {len(hotel_urls_to_process)} URLs ---")
                    # Load existing details results *before* starting the loop
                    self.load_existing_results()
                    new_details_added = 0
                    for i, url in enumerate(hotel_urls_to_process):
                        # Check if URL (or its base) was already processed from loaded data
                        base_url = url.split('?')[0]
                        if base_url in self.processed_urls_set:
                            logging.info(f"Skipping already processed URL ({i+1}/{len(hotel_urls_to_process)}): {base_url}")
                            continue

                        logging.info(f"--- Processing detail for URL {i+1}/{len(hotel_urls_to_process)}: {url} ---")

                        # --- Initialize driver FOR THIS URL ---
                        if not self._initialize_driver():
                            logging.error(f"Failed to initialize driver for URL {url}. Skipping this URL.")
                            continue # Skip to the next URL if driver init fails

                        details = None # Ensure details is defined
                        try:
                            # --- Get details using the newly initialized driver ---
                            details = self.get_hotel_details(url)

                            # Add details only if valid name found and not already processed
                            if details and details.get("name") != "N/A":
                                self.final_hotels_data.append(details)
                                self.processed_urls_set.add(base_url) # Add base URL to processed set
                                new_details_added += 1
                                logging.info(f"Successfully extracted: {details.get('name')}. Total details now: {len(self.final_hotels_data)}")
                                # Save incrementally after each successful detail extraction
                                self.save_results()
                            elif details and details.get("error"): # Handle specific driver init error case
                                logging.warning(f"Skipping storage for {url} due to error: {details.get('error')}")
                            else:
                                logging.warning(f"No valid details extracted for {url} or name was 'N/A'. Skipping storage.")

                        except Exception as detail_err:
                            # Catch errors that might happen *outside* get_hotel_details but within this loop iteration
                            logging.error(f"Unexpected error during detail processing loop for {url}: {detail_err}", exc_info=True)
                            if self.driver: self.driver.save_screenshot(f"error_detail_loop_unexpected_{time.time()}.png")
                        finally:
                            # --- Quit driver AFTER processing THIS URL ---
                            self._quit_driver()
                            logging.info(f"Driver quit after processing URL {i+1}.")

                            # Delay *after* quitting driver, before starting the next loop iteration (and next driver init)
                            sleep_time = random.uniform(1.0, 2.5) # Reduced delay
                            logging.debug(f"Sleeping for {sleep_time:.2f} seconds before next URL...")
                            time.sleep(sleep_time)

                    logging.info(f"--- Detail extraction phase complete. Added {new_details_added} new hotel details. ---")
            else:
                 logging.info("--- Skipping Phase 2: Detail Extraction (Disabled) ---")

        except Exception as e:
            # Catch errors during the overall orchestration (e.g., loading results)
            logging.critical(f"A critical error occurred during the full crawl orchestration: {e}", exc_info=True)
            # Attempt screenshot only if driver happens to exist at this point (unlikely)
            if self.driver:
                 try: self.driver.save_screenshot("critical_orchestration_error.png")
                 except: pass # Ignore screenshot errors here
        finally:
            # Final save regardless of errors
            self.save_results()
            # Ensure any lingering driver instance is quit (should already be handled in loop/phase 1 finally)
            if self.driver:
                 logging.warning("Driver instance still found in final finally block. Attempting quit.")
                 self._quit_driver()
            else:
                 logging.info("No active driver instance found in final finally block (expected).")

            end_time = time.time()
            logging.info(f"--- Full TripAdvisor Crawl Finished ---")
            logging.info(f"Total execution time: {end_time - start_time:.2f} seconds.")
            logging.info(f"Final total hotel details saved: {len(self.final_hotels_data)}")


    def save_results(self):
        """Saves the collected final hotel details to the JSON output file."""
        logging.info(f"Attempting to save {len(self.final_hotels_data)} hotel details to {self.output_file}...")
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(self.output_file) or '.', exist_ok=True)
            # Write data
            with open(self.output_file, 'w', encoding='utf-8') as f:
                json.dump(self.final_hotels_data, f, ensure_ascii=False, indent=2)
            logging.info(f"Save complete to {self.output_file}")
        except IOError as e:
            logging.error(f"Error saving data to {self.output_file}: {e}")
        except Exception as e:
            logging.error(f"An unexpected error occurred during saving results: {e}", exc_info=True)

    # --- ADD: Helper method to save URL list --- 
    def _save_url_list(self, url_list):
        """Saves the collected list of hotel URLs to a JSON file."""
        if not self.url_output_file:
            logging.warning("URL output file path not specified. Skipping URL list save.")
            return

        logging.info(f"Attempting to save {len(url_list)} collected URLs to {self.url_output_file}...")
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(self.url_output_file) or '.', exist_ok=True)
            # Write URL list data
            with open(self.url_output_file, 'w', encoding='utf-8') as f:
                json.dump(url_list, f, ensure_ascii=False, indent=2)
            logging.info(f"URL list save complete to {self.url_output_file}")
        except IOError as e:
            logging.error(f"Error saving URL list data to {self.url_output_file}: {e}")
        except Exception as e:
            logging.error(f"An unexpected error occurred during URL list saving: {e}", exc_info=True)
    # --- END ADD --- 

    def _append_url_to_file(self, url):
        """Appends a URL to the URL output file."""
        if not self.url_output_file:
            logging.warning("URL output file path not specified. Skipping URL append.")
            return

        logging.info(f"Appending URL: {url} to {self.url_output_file}")
        try:
            # Load existing URLs
            existing_urls = [] # Default to empty list
            try:
                with open(self.url_output_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if content:
                         existing_urls = json.loads(content)
                    if not isinstance(existing_urls, list):
                        logging.warning(f"URL file {self.url_output_file} does not contain a valid list. Resetting.")
                        existing_urls = []
            except FileNotFoundError:
                 logging.info(f"URL file {self.url_output_file} not found. Creating new file.")
                 existing_urls = [] # Start fresh if file doesn't exist
            except json.JSONDecodeError:
                 logging.warning(f"Could not decode JSON from {self.url_output_file}. Resetting file.")
                 existing_urls = [] # Start fresh if file is corrupt

            # --- Check for duplicates before appending --- 
            if url not in existing_urls:
                # Append new URL
                existing_urls.append(url)

                # Save updated URLs
                with open(self.url_output_file, 'w', encoding='utf-8') as f:
                    json.dump(existing_urls, f, ensure_ascii=False, indent=2)
                logging.info(f"URL appended successfully to {self.url_output_file}")
            else:
                 logging.debug(f"URL {url} already exists in {self.url_output_file}. Skipping append.")
            # --- End Check --- 

        except IOError as e:
            logging.error(f"IOError during URL append/save to {self.url_output_file}: {e}")


if __name__ == "__main__":
    # --- Configuration ---
    TARGET_URL_COUNT = 66 # How many hotel URLs to aim for (might get slightly more depending on page size)
    OUTPUT_FILE = "scrapper/data/tripadvisor_da_nang_final_details.json" # Final output file path
    URL_LIST_OUTPUT_FILE = "scrapper/data/tripadvisor_da_nang_collected_urls.json" # File for collected URLs

    # --- Control Flags --- # 
    RUN_URL_COLLECTION = True  # Set to False to skip URL collection and use existing URL file
    RUN_DETAIL_EXTRACTION = False # Set to False to skip detail extraction
    # --------------------- #

    logging.info(f"--- Initializing TripAdvisor Full Crawler ---")
    logging.info(f"Target URL Count: {TARGET_URL_COUNT}")
    logging.info(f"Details Output File: {OUTPUT_FILE}")
    logging.info(f"URL List Output File: {URL_LIST_OUTPUT_FILE}")
    logging.info(f"Run URL Collection: {RUN_URL_COLLECTION}")
    logging.info(f"Run Detail Extraction: {RUN_DETAIL_EXTRACTION}")

    if not RUN_URL_COLLECTION and not RUN_DETAIL_EXTRACTION:
        logging.warning("Both RUN_URL_COLLECTION and RUN_DETAIL_EXTRACTION are set to False. Exiting.")
    else:
        crawler = TripadvisorFullCrawler(output_detail_file=OUTPUT_FILE,
                                       url_target_count=TARGET_URL_COUNT,
                                       url_output_file=URL_LIST_OUTPUT_FILE,
                                       collect_urls=RUN_URL_COLLECTION,
                                       extract_details=RUN_DETAIL_EXTRACTION)
        crawler.run_full_crawl()

    # Optional: Final verification log
    logging.info("--- Final Verification ---")
    try:
        if os.path.exists(OUTPUT_FILE):
             with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
                final_data = json.load(f)
                logging.info(f"Successfully read back {len(final_data)} hotel details from {OUTPUT_FILE}")
        else:
             logging.error(f"Output file {OUTPUT_FILE} was not found after the crawl.")
    except Exception as e:
        logging.error(f"Error during final verification of {OUTPUT_FILE}: {e}")

    logging.info("--- Script Execution Complete ---")
