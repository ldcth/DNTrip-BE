import undetected_chromedriver as uc # Use undetected_chromedriver
# from selenium import webdriver # No longer directly needed for driver creation
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options # Keep for configuring options
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException, WebDriverException
import time
import json
import re
import os
import logging
import random # Import random for delays

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class TripadvisorCrawler:
    def __init__(self, output_file="tripadvisor_hotel_urls.json"): # Changed default output file
        opts = uc.ChromeOptions() # Use uc.ChromeOptions

        # --- Core Options ---
        # Comment out headless mode for debugging if needed
        opts.add_argument("--window-size=1920,1080")
        # Use a plausible, common user agent
        # opts.add_argument(
        #     f'--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36' # Example updated UA
        # )

        # --- Anti-Detection Related Options (potentially useful) ---
        # opts.add_argument('--disable-blink-features=AutomationControlled')
        # opts.add_argument('--ignore-certificate-errors') # Can be useful with proxies/certain sites

        # Use Tor SOCKS5 proxy directly
        # proxy_server = "127.0.0.1:9050" # Tor SOCKS5 default port
        # opts.add_argument(f'--proxy-server=socks5://{proxy_server}') 
        # logging.info(f"Using SOCKS5 proxy server: {proxy_server}") 
        logging.info(f"PROXY DISABLED - Using direct connection.") # Indicate proxy is off

        # Use undetected_chromedriver
        logging.info("Initializing undetected-chromedriver with revised options...")
        # Let uc.Chrome handle applying options, removed the try/except fallback for now
        self.driver = uc.Chrome(options=opts)

        logging.info("Waiting 10 seconds after driver initialization...")
        time.sleep(10) 
        logging.info("Driver initialized and waited.")

        self.wait = WebDriverWait(self.driver, 20) # Wait for list page elements
        # self.detail_wait = WebDriverWait(self.driver, 25) # Wait for detail page elements (can take longer) - Not needed for URL collection
        # Base URL for the initial page (no -oa0)
        self.base_url = "https://www.tripadvisor.com/Hotels-g298085-a_travelersChoice.1-Da_Nang-Hotels.html#SPLITVIEWLIST"
        # Template for subsequent pages (with -oa{offset})
        self.base_url_template = "https://www.tripadvisor.com/Hotels-g298085-oa{offset}-a_travelersChoice.1-Da_Nang-Hotels.html#SPLITVIEWLIST"
        self.output_file = output_file
        # self.hotels_data = [] # Replaced with URL list
        self.hotel_urls = [] # List to store collected URLs
        self.collected_urls_set = set() # Keep track of collected URLs to avoid duplicates

    # def extract_rating_count(self, text): # Keep commented out or remove if not needed for URL collection
    #     """Extracts the numerical rating count from text like '(1,234 reviews)'."""
    #     if not text:
    #         return "N/A"
    #     match = re.search(r'([\d,]+)\s+reviews?', text, re.IGNORECASE)
    #     if match:
    #         try:
    #             return int(match.group(1).replace(',', ''))
    #         except ValueError:
    #             return "N/A" # Should not happen with regex, but safety first
    #     return "N/A"

    # --- Commented out get_hotel_details ---
    # def get_hotel_details(self, hotel_url):
    #     """Opens hotel detail page in new tab, extracts info, and closes tab."""
    #     logging.info(f"Opening hotel detail page: {hotel_url}")
    #     original_window = self.driver.current_window_handle
    #     self.driver.switch_to.new_window('tab')
    #     # time.sleep(random.uniform(2.0, 4.0)) # Increased delay before loading new tab URL (Keep sleep after cookie clear)
    #     time.sleep(random.uniform(0.5, 1.5)) # Short pause after clearing cookies

    #     self.driver.get(hotel_url)
    #     # time.sleep(10)
    #     logging.info("Waiting after loading hotel detail page...")
    #     time.sleep(5)
    #     logging.info("Wait finished.")

    #     hotel_info = {"name": "N/A", "price": "N/A", "rating": "N/A", "rating_count": "N/A", "address": "N/A", "description": "N/A", "lat": None, "lon": None}

    #     try:
    #         # Wait for a key element like the name to ensure page is loaded
    #         self.detail_wait.until(EC.visibility_of_element_located((By.XPATH, "//div[contains(@class, 'WMndO') and contains(@class, 'f')]"))) # Wait for name element
    #         time.sleep(random.uniform(0.8, 1.8)) # Slightly increased delay after finding key element
    #         logging.info("Found key element on detail page.")

    #         # Price
    #         try:
    #             price_element = self.detail_wait.until(EC.visibility_of_element_located((By.XPATH, "//div[contains(@class, 'vyWtt')]")))
    #             hotel_info["price"] = price_element.text.strip()
    #         except (NoSuchElementException, TimeoutException):
    #             logging.warning(f"Could not find price for {hotel_url}")

    #         # Detail container: div.wWwSb.VogJa
    #         try:
    #             detail_container = self.detail_wait.until(EC.visibility_of_element_located((By.XPATH, "//div[contains(@class, 'wWwSb') and contains(@class, 'VogJa')]")))

    #             # Name
    #             try:
    #                 name_element = detail_container.find_element(By.XPATH, ".//h1[contains(@class, 'biGQs') and contains(@class, 'f')]")
    #                 hotel_info["name"] = name_element.text.strip()
    #             except NoSuchElementException:
    #                 logging.warning(f"Could not find name inside detail container for {hotel_url}")

    #             # Rating, Rating Count, Address - often siblings or near each other
    #             # Find all potential info spans/divs within the container
    #             info_elements = detail_container.find_elements(By.XPATH, ".//span[contains(@class, 'biGQs') and contains(@class, '_P') and contains(@class, 'pZUbB') and contains(@class, 'KxBGd')] | .//a[contains(@class, 'biGQs') and contains(@class, '_P') and contains(@class, 'pZUbB') and contains(@class, 'KxBGd')]") # Address might be a link

    #             for elem in info_elements:
    #                 elem_text = elem.text.strip()
    #                 # Rating (often has a specific SVG icon or aria-label)
    #                 try:
    #                     # Check for the bubble rating SVG's aria-label
    #                     svg_rating = elem.find_element(By.XPATH, './/svg[contains(@aria-label, "bubbles")]')
    #                     if svg_rating and hotel_info["rating"] == "N/A": # Take the first one found
    #                         hotel_info["rating"] = svg_rating.get_attribute('aria-label').strip()
    #                         continue # Move to next element
    #                 except NoSuchElementException:
    #                     pass # Not this element

    #                 # Rating Count (contains 'reviews')
    #                 if 'review' in elem_text.lower() and hotel_info["rating_count"] == "N/A":
    #                     # Use the previously defined function if uncommented
    #                     # hotel_info["rating_count"] = self.extract_rating_count(elem_text)
    #                     hotel_info["rating_count"] = elem_text # Or just store raw text for now
    #                     continue

    #                 # Address (often has a location icon nearby or specific keywords)
    #                 # This is heuristic - might need adjustment based on actual HTML structure
    #                 try:
    #                     # Check if the parent or the element itself contains location icon hints
    #                     # Using XPath to check for preceding sibling icon might be more robust if structure is fixed
    #                     # For now, just check if text looks like an address (very basic)
    #                     # and doesn't match rating/reviews patterns already handled.
    #                     # Check if the parent element is a specific address container if available
    #                     parent_div = elem.find_element(By.XPATH, "..") # Check parent element
    #                     # A better check would involve looking for specific map icons or markers
    #                     if hotel_info["address"] == "N/A" and hotel_info["rating"] != elem_text and not re.search(r'review', elem_text, re.I):
    #                          # Check if it's likely an address (crude check: contains comma or number)
    #                          if ',' in elem_text or any(char.isdigit() for char in elem_text):
    #                             hotel_info["address"] = elem_text

    #                 except Exception as e_addr:
    #                     logging.debug(f" Minor issue checking element for address: {e_addr}")


    #         except (NoSuchElementException, TimeoutException):
    #             logging.warning(f"Could not find main detail container (div.wWwSb.VogJa) for {hotel_url}")

    #         # Description: div.ythkR -> div._T FKffI TPznB Ci ajMTa Ps Z BB
    #         try:
    #             desc_container = self.detail_wait.until(EC.visibility_of_element_located((By.XPATH, "//div[contains(@class, 'ythkR')]")))
    #             description_element = desc_container.find_element(By.XPATH, ".//div[contains(@class, '_T') and contains(@class, 'FKffI') and contains(@class, 'TPznB') and contains(@class, 'Ci') and contains(@class, 'ajMTa') and contains(@class, 'Ps') and contains(@class, 'Z') and contains(@class, 'BB')]")
    #             hotel_info["description"] = description_element.text.strip()
    #         except (NoSuchElementException, TimeoutException):
    #             logging.warning(f"Could not find description for {hotel_url}")


    #     except TimeoutException:
    #         logging.error(f"Timeout waiting for elements on detail page: {hotel_url}")
    #         self.driver.save_screenshot(f"error_detail_timeout_{hotel_info.get('name', 'unknown')}.png")
    #     except WebDriverException as e:
    #          logging.error(f"WebDriverException on detail page {hotel_url}: {e}")
    #          self.driver.save_screenshot(f"error_detail_webdriver_{hotel_info.get('name', 'unknown')}.png")
    #     except Exception as e:
    #         logging.error(f"Unexpected error processing detail page {hotel_url}: {e}")
    #         self.driver.save_screenshot(f"error_detail_unexpected_{hotel_info.get('name', 'unknown')}.png")
    #     finally:
    #         logging.info(f"Closing tab for: {hotel_url}")
    #         self.driver.close()
    #         self.driver.switch_to.window(original_window)
    #         time.sleep(random.uniform(2.0, 4.0)) # Further increased wait after closing tab

    #     # Add only if name was found
    #     if hotel_info["name"] != "N/A":
    #         # self.hotels_data.append(hotel_info) # Don't append hotel data here
    #         # self.scraped_hotel_urls.add(hotel_url) # Add to set of processed URLs - This happens in start_crawl now
    #         logging.info(f"Successfully extracted: {hotel_info['name']}. Total: {len(self.hotel_urls)}") # Log based on URL count
    #         # self.save_results() # Save incrementally - Save after each page or at the end now
    #         return True
    #     else:
    #          logging.warning(f"Failed to extract sufficient details for {hotel_url}. Skipping.")
    #          return False
    # --- End Commented out get_hotel_details ---

    def select_checkin_checkout_dates(self):
        """Performs a specific button click sequence potentially related to date/filters."""
        logging.info("Attempting specific button click sequence...")
        try:
            # time.sleep(random.uniform(1.0, 2.0)) # Delay before starting sequence
            time.sleep(random.uniform(1.5, 3.0)) # Increased delay before starting sequence
            # 1. Find the outer container div using exact class match
            outer_container_selector = "//div[@class='SKCqA _T R2 f e qhZKQ']"
            logging.info(f"Waiting for outer container: {outer_container_selector}")
            outer_container = self.wait.until(EC.visibility_of_element_located((By.XPATH, outer_container_selector)))
            logging.info("Outer container found.")

            # 2. Find the inner div inside the outer container using exact class match
            inner_container_selector = ".//div[@class='oljCt Pj PN Pw PA Z BB']"
            logging.info(f"Finding inner container within outer: {inner_container_selector}")
            inner_container = outer_container.find_element(By.XPATH, inner_container_selector)
            logging.info("Inner container found.")

            # 3. Find all buttons matching the exact class within the inner container
            button_selector = ".//button[@class='rmyCe _G B- z _S c Wc wSSLS jWkoZ QHaGY']"
            logging.info(f"Finding buttons matching selector: {button_selector} within inner container")
            buttons = inner_container.find_elements(By.XPATH, button_selector)
            logging.info(f"Found {len(buttons)} matching buttons.")

            # 4. Click the second button (index 1)
            if len(buttons) >= 2:
                second_button = buttons[1] # Python list index is 0-based
                # Log the text from the span inside the button
                try:
                    # Find span within the button
                    span_element = second_button.find_element(By.XPATH, ".//span")
                    button_text = span_element.text.strip() if span_element.text else "[Span has no text]"
                    logging.info(f"Found second button. Inner span text: '{button_text}'. Attempting to click button...")
                except NoSuchElementException:
                    logging.warning("Could not find span inside the second button. Attempting to click button anyway...")
                except Exception as text_err:
                     logging.warning(f"Could not get text of inner span: {text_err}. Attempting to click button anyway...")

                # Proceed with clicking the button using JavaScript
                try:
                    # Scroll into view first using JavaScript for potentially better centering
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", second_button)
                    # time.sleep(random.uniform(0.8, 1.5)) # Increased pause after scroll
                    time.sleep(random.uniform(1.0, 2.0)) # Slightly increased pause after scroll
                    # Use JavaScript to click, bypassing interception checks
                    self.driver.execute_script("arguments[0].click();", second_button)
                    logging.info("Clicked the second button via JavaScript.")
                    # Wait a moment for any action triggered by the click
                    # time.sleep(random.uniform(3.5, 5.0)) # Increased wait after click
                    time.sleep(random.uniform(4.0, 7.0)) # Further increased wait after click

                    # --- Start: New sequence to click the final button ---
                    logging.info("Starting new sequence to find and click final button...")
                    try:
                        # Find div class PeChA IPdZD GTGpm
                        final_container_1_selector = "//div[@class='PeChA IPdZD GTGpm']"
                        logging.info(f"Looking for final container 1: {final_container_1_selector}")
                        final_container_1 = self.wait.until(EC.visibility_of_element_located((By.XPATH, final_container_1_selector)))
                        logging.info("Found final container 1.")

                        # Inside it, find div class EcOjx
                        final_container_2_selector = ".//div[@class='EcOjx']"
                        logging.info(f"Looking for final container 2 inside container 1: {final_container_2_selector}")
                        final_container_2 = final_container_1.find_element(By.XPATH, final_container_2_selector)
                        logging.info("Found final container 2.")

                        # Inside it, find button class BrOJk u j z _F wSSLS tIqAi iNBVo and click
                        final_button_selector = ".//button[@class='BrOJk u j z _F wSSLS tIqAi iNBVo']"
                        logging.info(f"Looking for final button: {final_button_selector}")
                        final_button = self.wait.until(EC.element_to_be_clickable((By.XPATH, final_container_2_selector + final_button_selector[1:]))) # Combine selectors, wait for clickable
                        logging.info("Found final button. Clicking...")
                        final_button.click()
                        logging.info("Clicked final button.")
                        # time.sleep(random.uniform(1.5, 2.5)) # Increased pause after final click
                        time.sleep(random.uniform(2.0, 4.0)) # Further increased pause after final click

                    except (NoSuchElementException, TimeoutException) as final_err:
                        logging.error(f"Error during final button click sequence: {final_err}")
                        self.driver.save_screenshot("error_final_button_sequence.png")
                    # --- End: New sequence ---

                except Exception as click_err:
                     logging.error(f"Failed to click the second button even with JavaScript: {click_err}")
                     self.driver.save_screenshot("error_js_click_failed.png")
            else:
                logging.warning(f"Could not find the second button matching the selector. Found {len(buttons)} buttons.")
                # Optionally save screenshot if the expected button isn't found
                self.driver.save_screenshot("error_button_not_found.png")

            logging.info("Button click sequence complete.")

        except (NoSuchElementException, TimeoutException) as e:
            logging.error(f"Error during button click sequence: {e}")
            self.driver.save_screenshot("error_button_sequence.png")
            logging.warning("Proceeding without completing button click sequence due to error.")
        except Exception as e:
            logging.error(f"An unexpected error occurred during button click sequence: {e}")
            self.driver.save_screenshot("error_button_sequence_unexpected.png")
            logging.warning("Proceeding without completing button click sequence due to error.")

    def start_crawl(self, target_url_count=60): # Renamed target_count
        """Starts the crawling process to collect TripAdvisor hotel URLs."""
        if os.path.exists(self.output_file):
            logging.info(f"Output file {self.output_file} exists. Loading previous URLs.")
            try:
                with open(self.output_file, 'r', encoding='utf-8') as f:
                    # self.hotels_data = json.load(f) # Load URLs now
                    self.hotel_urls = json.load(f)
                    # Populate collected URLs set from loaded data
                    self.collected_urls_set = set(self.hotel_urls)
                    logging.info(f"Loaded {len(self.hotel_urls)} URLs.")
            except (json.JSONDecodeError, IOError) as e:
                 logging.error(f"Error loading existing file {self.output_file}: {e}. Starting fresh.")
                 self.hotel_urls = []
                 self.collected_urls_set = set()
                 if os.path.exists(self.output_file):
                     os.remove(self.output_file) # Remove corrupted file
                 with open(self.output_file, 'w') as f:
                     json.dump([], f) # Create an empty JSON array
        else:
            logging.info("No existing output file found. Starting fresh.")
            self.hotel_urls = []
            self.collected_urls_set = set()
            with open(self.output_file, 'w') as f:
                json.dump([], f) # Create empty file


        offset = 0
        max_hotels_per_page = 30 # TripAdvisor seems to show 30 per page
        # Calculate starting offset based on already collected URLs only if we need to resume
        if self.hotel_urls: # Check if list is not empty
             # Base offset calculation on loaded URLs
             # Note: This assumes URLs were collected sequentially page by page.
             # A more robust approach might involve checking the last URL's original page context if possible.
             offset = (len(self.hotel_urls) // max_hotels_per_page) * max_hotels_per_page
             logging.info(f"Resuming crawl, starting offset calculated based on {len(self.hotel_urls)} existing URLs: {offset}")
        else:
             offset = 0 # Start from the beginning if fresh start or no data loaded
             logging.info("Starting fresh URL crawl from offset 0.")


        try:
            # --- Load initial page (offset 0) and select dates ---
            logging.info(f"Loading initial page for button sequence: {self.base_url}")
            self.driver.get(self.base_url)
            time.sleep(random.uniform(4.0, 6.0)) # Increased wait for initial load
            logging.info("Initial page loaded, proceeding to button sequence.")

            self.select_checkin_checkout_dates() # Perform button click sequence
            logging.info("Button sequence finished, starting main URL collection loop.")

            # --- Main Crawling Loop ---
            # while len(self.hotels_data) < target_count: # Changed condition
            while len(self.hotel_urls) < target_url_count:
                # Determine the correct URL for the current offset
                if offset == 0:
                    expected_url = self.base_url
                    logging.info(f"Processing page offset 0: {expected_url}")
                else:
                    expected_url = self.base_url_template.format(offset=offset)
                    logging.info(f"Processing page offset {offset}: {expected_url}")

                # Navigate to the expected URL if not already there
                if self.driver.current_url != expected_url:
                     logging.info(f"Current URL {self.driver.current_url} doesn't match expected. Navigating...")
                     self.driver.get(expected_url)
                     time.sleep(random.uniform(6.0, 9.0)) # Further increased wait for navigation
                     logging.info(f"Navigation to {expected_url} complete.")

                page_url = self.driver.current_url # Use current URL after potential navigation
                # logging.info(f"Now processing page: {page_url} (Target: {target_count}, Current: {len(self.hotels_data)})") # Changed log
                logging.info(f"Now processing page: {page_url} (Target URLs: {target_url_count}, Current URLs: {len(self.hotel_urls)})")

                try:
                    # Wait for the main hotel list container
                    hotel_list_container_selector = "//div[contains(@class, 'oobXg')]"
                    self.wait.until(EC.visibility_of_element_located((By.XPATH, hotel_list_container_selector)))
                    list_container = self.driver.find_element(By.XPATH, hotel_list_container_selector)

                    # Find hotel 'li' elements within the container
                    hotel_elements_selector = ".//li[contains(@class, 'cauVP')]" # Found this class on li elements 04/07/2024, might change
                    hotel_list_items = list_container.find_elements(By.XPATH, hotel_elements_selector)
                    logging.info(f"Found {len(hotel_list_items)} potential hotel items on page.")

                    if not hotel_list_items:
                        logging.warning("No hotel list items found on the page. Trying different selector or stopping.")
                         # Try a broader li search within the container as fallback
                        hotel_list_items = list_container.find_elements(By.TAG_NAME, 'li')
                        logging.info(f"Found {len(hotel_list_items)} items using broader 'li' tag search.")
                        if not hotel_list_items:
                           logging.error("Still no hotel items found. Ending crawl.")
                           break # Exit outer loop if no hotels found

                    collected_on_page = 0 # Track URLs collected on this page
                    for i, item in enumerate(hotel_list_items):
                        logging.debug(f"Processing item {i+1}/{len(hotel_list_items)}")
                        # Scroll item into view gently
                        try:
                           self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", item)
                           time.sleep(random.uniform(0.6, 1.2)) # Randomized short pause after scroll
                        except Exception as scroll_err:
                           logging.warning(f"Could not scroll item into view: {scroll_err}")


                        # Find the primary link to the hotel details page
                        hotel_link_selector = ".//a[@class='BMQDV _F Gv wSSLS SwZTJ w']" # Changed from // to .// to be relative

                        try:
                            hotel_link_element = item.find_element(By.XPATH, hotel_link_selector)
                            hotel_url = hotel_link_element.get_attribute('href')
                            original_url_with_query = hotel_url # Keep for logging/debugging

                            # --- STRIP QUERY PARAMETERS ---
                            if hotel_url and '?' in hotel_url:
                                hotel_url = hotel_url.split('?')[0]
                                # logging.info(f"Stripped query parameters. Original: {original_url_with_query}, Using: {hotel_url}") # Log only if new
                            # --- END STRIP ---

                            if hotel_url and hotel_url not in self.collected_urls_set:
                                logging.info(f"Found new unique hotel URL (query stripped): {hotel_url} (Original: {original_url_with_query})")
                                self.hotel_urls.append(hotel_url)
                                self.collected_urls_set.add(hotel_url)
                                collected_on_page += 1
                                self.save_results() # Save incrementally after finding a new URL
                                if len(self.hotel_urls) >= target_url_count:
                                    logging.info(f"Reached target URL count of {target_url_count}. Stopping.")
                                    break # Exit item loop
                            elif hotel_url in self.collected_urls_set:
                                logging.debug(f"Already collected URL: {hotel_url}. Skipping.")
                            else:
                                logging.warning("Found link element but no href attribute.")

                        except NoSuchElementException:
                            logging.debug(f"Could not find primary hotel link ({hotel_link_selector}) in this list item.")
                            # Removed the fallback button logic as we only want URLs from the main link


                    # Check if target count is reached after processing the page
                    # if len(self.hotels_data) >= target_count: # Changed condition
                    if len(self.hotel_urls) >= target_url_count:
                        break # Exit outer loop

                    # Small delay before processing next page or stopping
                    logging.info(f"Finished processing items on page {page_url}. Found {collected_on_page} new URLs. Pausing before next page...")
                    time.sleep(random.uniform(2.0, 4.5)) # Increased delay before potentially loading next page

                    # Move to the next page
                    # Only advance if we found items on the page, even if no *new* URLs were collected (to avoid getting stuck)
                    if len(hotel_list_items) > 0:
                        offset += max_hotels_per_page
                    else:
                         logging.warning(f"No hotel list items found on page with offset {offset}. Stopping pagination.")
                         break # Stop if a page yielded no list items

                except (TimeoutException, NoSuchElementException) as e:
                    logging.error(f"Could not find hotel list container or critical element on page {page_url}: {e}")
                    self.driver.save_screenshot(f"error_list_page_{offset}.png")
                    break # Stop if the list page structure isn't found
                except Exception as e:
                     logging.error(f"An unexpected error occurred processing page {page_url}: {e}")
                     self.driver.save_screenshot(f"error_list_page_unexpected_{offset}.png")
                     break # Stop on unexpected errors


            # logging.info(f"Crawling finished. Scraped {len(self.hotels_data)} hotels.") # Changed log
            logging.info(f"URL collection finished. Collected {len(self.hotel_urls)} unique URLs.")

        except WebDriverException as e:
             logging.critical(f"A WebDriverException occurred during the URL collection: {e}")
             self.driver.save_screenshot("critical_crawl_webdriver_error.png")
        except Exception as e:
            logging.critical(f"A critical error occurred during URL collection: {e}")
            self.driver.save_screenshot("critical_crawl_error.png")
        finally:
            self.save_results() # Save whatever was collected
            self.driver.quit()
            logging.info("WebDriver closed.")

    def save_results(self):
        """Saves the collected URLs to a JSON file."""
        try:
            # logging.info(f"Saving {len(self.hotels_data)} hotels to {self.output_file}...") # Changed log
            logging.info(f"Saving {len(self.hotel_urls)} URLs to {self.output_file}...")
            with open(self.output_file, 'w', encoding='utf-8') as f:
                # json.dump(self.hotels_data, f, ensure_ascii=False, indent=2) # Save URLs
                json.dump(self.hotel_urls, f, ensure_ascii=False, indent=2)
            logging.info("Save complete.")
        except IOError as e:
            logging.error(f"Error saving data to {self.output_file}: {e}")
        except Exception as e:
            logging.error(f"An unexpected error occurred during saving: {e}")


if __name__ == "__main__":
    target_url_count = 30 # Set target URL count
    # crawler = TripadvisorCrawler(output_file="tripadvisor_da_nang_hotels.json") # Use new filename
    crawler = TripadvisorCrawler(output_file="tripadvisor_da_nang_hotel_urls.json")
    crawler.start_crawl(target_url_count=target_url_count)

    # Optional: Check final count and report
    try:
        with open(crawler.output_file, 'r', encoding='utf-8') as f:
            # final_data = json.load(f) # Load URLs
            final_urls = json.load(f)
            # logging.info(f"Final check: {len(final_data)} hotels found in {crawler.output_file}") # Changed log
            logging.info(f"Final check: {len(final_urls)} URLs found in {crawler.output_file}")
            # if len(final_data) < target_hotel_count: # Changed condition
            if len(final_urls) < target_url_count:
                 # logging.warning(f"Warning: Target count of {target_hotel_count} hotels was not reached (found {len(final_data)}).") # Changed log
                 logging.warning(f"Warning: Target URL count of {target_url_count} was not reached (found {len(final_urls)}).")
    except FileNotFoundError:
        logging.error(f"Error: {crawler.output_file} not found after crawl.")
    except json.JSONDecodeError:
         logging.error(f"Error: {crawler.output_file} is not valid JSON.")
