import selenium
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException
from selenium.webdriver.common.action_chains import ActionChains
import time
import json
import re
import os
import logging # Import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class BedlinkerCrawler:
    def __init__(self, output_file="hotels.json"):
        opts = Options()
        # Comment out headless mode for debugging if needed
        # opts.add_argument("--headless=new")
        opts.add_argument("--window-size=1920,1080") # Ensure viewport is large enough
        self.driver = webdriver.Chrome(options=opts)
        self.wait = WebDriverWait(self.driver, 20) # Increased wait time
        self.detail_wait = WebDriverWait(self.driver, 15) # Wait time for detail card
        self.initial_URL = "https://bedlinker.vn/hotels"
        self.output_file = output_file
        self.hotels_data = []
        self.scraped_hotel_names = set()

    def search_location(self):
        """Searches for the specified location on the page."""
        logging.info(f"Searching for location: {self.location_name}")
        try:
            # Increase initial delay after page load
            time.sleep(5) # Allow more time for page elements to settle

            # Wait for the location selection trigger div (using text content)
            
            location_trigger_xpath = "/html/body/div/div/main/div/div[1]/div/div[1]/div/div[1]/div[1]/div/div/div/div/span[1]/input"
            logging.info(f"Waiting for search trigger visibility: {location_trigger_xpath}")
            # Wait for visibility first
            search_trigger_visible = self.wait.until(
                EC.visibility_of_element_located((By.XPATH, location_trigger_xpath))
            )
            logging.info("Search trigger div visible.")

            search_trigger_visible.send_keys(self.location_name)
            # search_trigger_visible.send_keys(Keys.RETURN)   

            time.sleep(2) # Short wait for input to appear

            ActionChains(self.driver)\
                .key_down(Keys.ARROW_DOWN)\
                .key_up(Keys.ARROW_DOWN)\
                .send_keys(Keys.ENTER)\
                .perform()

            # select_location = self.wait.until(
            #     EC.visibility_of_element_located((By.XPATH, "xpath=//div[@id='rc_select_4_list_2']/div"))
            # )
            # logging.info("Search trigger div visible.")
            # select_location.click()
            time.sleep(2)

            submit_location = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "/html/body/div[1]/div/main/div/div[1]/div/div[1]/div/div[1]/div[7]/button"))
            )
            submit_location.click()
            time.sleep(5)

            # # Then wait for clickability
            # logging.info(f"Waiting for search trigger clickability: {location_trigger_xpath}")
            # search_trigger = self.wait.until(
            #     EC.element_to_be_clickable((By.XPATH, location_trigger_xpath))
            # )
            # logging.info("Search trigger div found and clickable.")
            # search_trigger.click()
            # logging.info("Clicked search trigger div.")
            # time.sleep(1) # Short wait for input to appear

            # # Wait for the search input field to be visible
            # search_input_selector = "input.ant-select-selection-search-input"
            # logging.info(f"Waiting for search input: {search_input_selector}")
            # search_input = self.wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, search_input_selector)))
            # search_input.send_keys(self.location_name)
            # logging.info(f"Entered '{self.location_name}' into search input.")
            # time.sleep(1) # Wait for dropdown options to filter

            # # Wait for the specific location option to appear in the dropdown
            # # Use a more specific XPath that targets the option text within the dropdown structure
            # # location_option_xpath = f"//div[contains(@class, 'ant-select-item-option-content')]//span[contains(text(),'{self.location_name}')]"
            # # logging.info(f"Waiting for location option: {location_option_xpath}")
            # # location_option = self.wait.until(
            # #     EC.element_to_be_clickable((By.XPATH, location_option_xpath))
            # # )

            # # # Click the location option
            # # # location_option.click()
            # # # logging.info(f"Selected '{self.location_name}' from dropdown.")
            # # # time.sleep(1) # Wait for selection to register

            # # # Click the search button
            # # # search_button_xpath = "//button[contains(., 'Tìm kiếm')]"
            # # # logging.info(f"Waiting for search button: {search_button_xpath}")
            # # # search_button = self.wait.until(
            # # #     EC.element_to_be_clickable((By.XPATH, search_button_xpath))
            # # # )
            # # # search_button.click()
            # # # logging.info("Clicked Search button.")
            # # # time.sleep(5) # Wait for search results to load

        except TimeoutException as e:
            logging.error(f"Timeout waiting for element during location search: {e}")
            self.driver.save_screenshot("location_search_timeout_error.png")
            raise  # Re-raise the exception to signal failure
        except Exception as e:
            logging.error(f"An unexpected error occurred during location search: {e}")
            self.driver.save_screenshot("location_search_unexpected_error.png")
            raise # Re-raise the exception

    def get_list_view_info(self, card_element):
        """Extracts information from a hotel card in the list view."""
        # Initialize with null lat/lon
        info = {"name": "N/A", "price": "N/A", "address": "N/A", "rating": "N/A", "rating_count": "N/A", "lat": None, "lon": None}
        try:
            # Name
            try:
                name_element = card_element.find_element(By.CSS_SELECTOR, 'span.ant-typography[style*="font-size: 20px"]')
                info["name"] = name_element.text.strip()
            except NoSuchElementException:
                print("Warning: Could not find hotel name.")

            # Price
            try:
                price_element = card_element.find_element(By.CSS_SELECTOR, 'span.ant-typography[style*="font-size: 17px"]')
                info["price"] = price_element.text.strip()
            except NoSuchElementException:
                 print(f"Warning: Could not find price for {info['name']}.")

            # Address
            try:
                # This selector might be fragile, adjust if needed
                address_element = card_element.find_element(By.CSS_SELECTOR, 'span.ant-typography[style*="color: rgb(143, 143, 143)"][style*="font-size: 14px"]')
                info["address"] = address_element.text.strip()
            except NoSuchElementException:
                print(f"Warning: Could not find address for {info['name']}.")

            # Rating & Rating Count (within the same parent div)
            try:
                rating_div = card_element.find_element(By.CSS_SELECTOR, 'div.ant-row[style*="gap: 12px"]')
                # Rating
                try:
                    rating_element = rating_div.find_element(By.CSS_SELECTOR, 'span.ant-typography[style*="color: rgb(0, 170, 108)"]')
                    info["rating"] = rating_element.text.strip()
                except NoSuchElementException:
                    print(f"Warning: Could not find rating for {info['name']}.")

                # Rating Count
                try:
                    rating_count_element = rating_div.find_element(By.CSS_SELECTOR, 'span.ant-typography[style*="color: rgb(58, 134, 255)"]')
                    count_text = rating_count_element.text.strip()
                    match = re.search(r'\((\d+)\)', count_text)
                    if match:
                        info["rating_count"] = match.group(1)
                    else:
                         print(f"Warning: Could not parse rating count '{count_text}' for {info['name']}.")
                         info["rating_count"] = count_text # Store raw text if parsing fails
                except NoSuchElementException:
                    print(f"Warning: Could not find rating count for {info['name']}.")

            except NoSuchElementException:
                 print(f"Warning: Could not find rating container div for {info['name']}.")

        except StaleElementReferenceException:
            print("Warning: Stale element reference encountered while extracting list view info. Skipping this card.")
            return None # Indicate failure
        except Exception as e:
            print(f"An unexpected error occurred extracting list info for '{info.get('name', 'Unknown')}': {e}")

        return info

    def get_detail_view_info(self, list_card_element):
        """Clicks 'Chi tiết', extracts description, and closes the detail card."""
        detail_info = {"description": "N/A"}
        try:
            # Click "Chi tiết" button within the card
            detail_button_xpath = ".//button/span[contains(text(), 'Chi tiết')]/parent::button"
            detail_button = list_card_element.find_element(By.XPATH, detail_button_xpath)
            # Scroll button into view if necessary
            self.driver.execute_script("arguments[0].scrollIntoViewIfNeeded(true);", detail_button)
            time.sleep(0.5)
            detail_button.click()
            # print(f"Clicked 'Chi tiết' for {list_card_element.find_element(By.CSS_SELECTOR, 'span.ant-typography[style*=\"font-size: 20px\"]').text}") # Log which hotel detail is opened
            time.sleep(1) # Allow modal transition

            # Wait for the detail card to be visible and find description
            detail_card_xpath = "/html/body/div[1]/div/main/div/div[2]"
            detail_card = self.detail_wait.until(EC.visibility_of_element_located((By.XPATH, detail_card_xpath)))
            time.sleep(1) # Extra wait for content rendering within the modal

            try:
                 # More specific selector for description within the detail card's body
                description_xpath = "/html/body/div[1]/div/main/div/div[2]/div/div[2]/div[2]/div[2]/div[1]/div/div/div[4]" # Assume description is a longer span
                description_element = detail_card.find_element(By.XPATH, description_xpath)
                detail_info["description"] = description_element.text.strip()
            except NoSuchElementException:
                 print("Warning: Could not find description element in detail view. Trying alternative selector.")
                 try:
                     # Fallback selector if the first one fails
                     alt_description_xpath = ".//div[contains(@class, 'ant-card-body')]//div[@class='ant-row css-3ap8i']/span[@class='ant-typography css-3ap8i']"
                     description_element = detail_card.find_element(By.XPATH, alt_description_xpath)
                     detail_info["description"] = description_element.text.strip()
                 except NoSuchElementException:
                      print("Error: Could not find description element with fallback selector either.")
                      self.driver.save_screenshot("detail_description_error.png")


            # Find and click the close button
            close_button_xpath = "/html/body/div[1]/div/main/div/div[2]/div/div[1]/div/div/button"
            close_button = self.detail_wait.until(EC.element_to_be_clickable((By.XPATH, close_button_xpath)))
            close_button.click()
            print("Clicked close button on detail card.")
            time.sleep(1.5) # Wait for modal to close and list view to stabilize

        except TimeoutException:
            print("Error: Timed out waiting for detail card or close button.")
            self.driver.save_screenshot("detail_timeout_error.png")
             # Try to recover if possible, e.g., refresh or attempt closing differently
            try: # Attempt to force close if button click failed
                close_button_xpath = "/html/body/div[1]/div/main/div/div[2]/div/div[1]/div/div/button"
                if self.driver.find_elements(By.XPATH, close_button_xpath):
                    print("Attempting to force close detail card...")
                    self.driver.find_element(By.XPATH, close_button_xpath).click()
                    time.sleep(1)
            except Exception as close_err:
                print(f"Could not force close detail card: {close_err}")

        except StaleElementReferenceException:
             print("Warning: Stale element reference encountered in detail view. Skipping detail extraction for this card.")
        except Exception as e:
            print(f"An unexpected error occurred during detail view processing: {e}")
            self.driver.save_screenshot("detail_unexpected_error.png")

        return detail_info

    def scroll_results(self):
        """Scrolls the results pane down."""
        try:
            scrollable_element_xpath = '//div[contains(@class, "ant-flex") and contains(@style, "overflow: auto")]'
            scroll_pane = self.wait.until(EC.presence_of_element_located((By.XPATH, scrollable_element_xpath)))
            last_height = self.driver.execute_script("return arguments[0].scrollHeight", scroll_pane)
            print(f"Scrolling down. Current scrollHeight: {last_height}")

            self.driver.execute_script("arguments[0].scrollTo(0, arguments[0].scrollHeight);", scroll_pane)
            time.sleep(5) # Crucial: Wait for content to load after scroll

            new_height = self.driver.execute_script("return arguments[0].scrollHeight", scroll_pane)
            print(f"New scrollHeight after scroll: {new_height}")

            if new_height == last_height:
                print("Reached end of scroll (or no new content loaded).")
                return False # Indicate no more scrolling possible or needed
            return True # Indicate successful scroll
        except TimeoutException:
            print("Error: Timed out waiting for scrollable element.")
            return False
        except Exception as e:
            print(f"An error occurred during scrolling: {e}")
            return False

    def start_crawl(self, location_name, target_count=30):
        """Starts the crawling process."""
        self.location_name = location_name # Set the location name for this crawl
        max_scroll_failures = 5 # Maximum times to retry scrolling if it fails
        consecutive_scroll_failures = 0

        # Clear the output file at the beginning
        if os.path.exists(self.output_file):
            os.remove(self.output_file)
            print(f"Removed existing file: {self.output_file}")
        with open(self.output_file, 'w') as f:
            json.dump([], f) # Create an empty JSON array

        self.driver.get(self.initial_URL)
        try:
            self.search_location()

            while len(self.hotels_data) < target_count:
                print("-" * 20)
                print(f"Current hotel count: {len(self.hotels_data)} / {target_count}")
                new_hotels_found_in_pass = False

                # Find hotel cards
                hotel_cards_xpath = '//div[contains(@class, "ant-flex") and contains(@style, "margin-bottom: 24px")]'
                try:
                    # Wait for at least one card to be present or refresh if needed
                    self.wait.until(EC.presence_of_element_located((By.XPATH, hotel_cards_xpath)))
                    cards = self.driver.find_elements(By.XPATH, hotel_cards_xpath)
                    print(f"Found {len(cards)} hotel cards in current view.")
                except TimeoutException:
                    print("Warning: No hotel cards found in the current view after waiting.")
                    cards = [] # Ensure cards is iterable

                card_index = 0
                while card_index < len(cards):
                    # Re-find the card element in each iteration to avoid staleness
                    try:
                        current_cards = self.driver.find_elements(By.XPATH, hotel_cards_xpath)
                        if card_index >= len(current_cards):
                            print("Warning: Card index out of bounds after potential DOM change. Breaking inner loop.")
                            break # Exit if the number of cards changed unexpectedly
                        card = current_cards[card_index]

                        # Check if card is visible before interacting
                        if not card.is_displayed():
                             print(f"Card {card_index + 1} is not visible, scrolling slightly.")
                             self.driver.execute_script("arguments[0].scrollIntoViewIfNeeded(true);", card)
                             time.sleep(0.5)
                             # Re-check visibility after scroll
                             if not card.is_displayed():
                                 print(f"Card {card_index + 1} still not visible after scroll. Skipping.")
                                 card_index += 1
                                 continue # Indented correctly

                        list_info = self.get_list_view_info(card)

                        if list_info and list_info["name"] != "N/A" and list_info["name"] not in self.scraped_hotel_names:
                            print(f"Processing new hotel: {list_info['name']}")
                            detail_info = self.get_detail_view_info(card) # Pass the specific card element

                            if detail_info:
                                combined_info = {**list_info, **detail_info}
                                self.hotels_data.append(combined_info)
                                self.scraped_hotel_names.add(list_info["name"])
                                new_hotels_found_in_pass = True
                                print(f"Successfully added: {list_info['name']}. Total: {len(self.hotels_data)}")

                                # Save incrementally
                                self.save_results()

                                if len(self.hotels_data) >= target_count:
                                    print(f"Reached target count of {target_count}. Stopping.")
                                    break # Exit inner loop
                        elif list_info and list_info["name"] in self.scraped_hotel_names:
                            print(f"Skipping duplicate hotel: {list_info['name']}")
                        elif not list_info:
                             print(f"Skipping card {card_index + 1} due to extraction error in list view.") # Corrected alignment

                    except StaleElementReferenceException:
                        print(f"Warning: Stale element reference for card index {card_index}. Re-finding cards.")
                        # Cards list might be outdated, break and re-fetch in the next outer loop iteration
                        break
                    except Exception as e:
                        print(f"An error occurred processing card index {card_index}: {e}")
                        # Optionally add a screenshot here for debugging specific card errors
                        # self.driver.save_screenshot(f"card_{card_index}_error.png")

                    card_index += 1 # Move to the next card

                # Check if target count is reached after processing cards in the current view
                if len(self.hotels_data) >= target_count:
                     break # Exit outer loop

                # Scroll only if more hotels are needed and new ones were found in the last pass OR if we haven't failed scrolling too many times
                if new_hotels_found_in_pass or consecutive_scroll_failures < max_scroll_failures :
                    if self.scroll_results():
                        consecutive_scroll_failures = 0 # Reset counter on successful scroll
                    else:
                        consecutive_scroll_failures += 1
                        print(f"Scroll failed ({consecutive_scroll_failures}/{max_scroll_failures}).")
                        if consecutive_scroll_failures >= max_scroll_failures:
                            print("Max scroll failures reached. Stopping scroll attempts.")
                            break # Stop if scrolling fails repeatedly
                else:
                    print("No new hotels found in the last pass and no scroll failures yet. Assuming end of results.")
                    break # Assume end of results if no new hotels found

            print(f"Crawling finished. Scraped {len(self.hotels_data)} hotels.")

        # Correctly aligned main exception handler
        except Exception as e:
            print(f"An critical error occurred during crawling: {e}")
            self.driver.save_screenshot("critical_crawl_error.png")
        finally:
            self.save_results() # Save whatever was collected
            self.driver.quit()
            print("WebDriver closed.")

    def save_results(self):
        """Saves the scraped data to a JSON file."""
        try:
            print(f"Saving {len(self.hotels_data)} hotels to {self.output_file}...")
            with open(self.output_file, 'w', encoding='utf-8') as f:
                json.dump(self.hotels_data, f, ensure_ascii=False, indent=2)
            print("Save complete.")
        except IOError as e:
            print(f"Error saving data to {self.output_file}: {e}")
        except Exception as e:
            print(f"An unexpected error occurred during saving: {e}")


if __name__ == "__main__":
    target_count = 10
    crawler = BedlinkerCrawler(output_file="bedlinker_hotels.json")
    crawler.start_crawl(location_name="Da Nang", target_count=target_count)

    # Optional: Check final count and report
    try:
        with open("bedlinker_hotels.json", 'r', encoding='utf-8') as f:
            final_data = json.load(f)
            print(f"Final check: {len(final_data)} hotels found in bedlinker_hotels.json")
            if len(final_data) < target_count:
                 print(f"Warning: Target count of {target_count} hotels was not reached.")
    except FileNotFoundError:
        print("Error: bedlinker_hotels.json not found after crawl.")
    except json.JSONDecodeError:
         print("Error: bedlinker_hotels.json is not valid JSON.")
