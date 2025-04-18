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
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
            logging.info(f"Created output directory: {self.output_dir}")

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

    def _scrape_flight_details(self, flight_element):
        """Extracts details from a single flight element and its popup."""
        flight_data = {}
        try:
            # --- Extract Price from List View ---
            # NOTE: Using the absolute XPath provided by the user. This is VERY fragile.
            price_xpath = ".//div[contains(@class, 'oVHK')]"
            # price_xpath = "/html/body/div[2]/div/div[1]/div[3]/div[2]/div/div/div[5]/div[2]/div/div[1]/div[2]/div/div[2]/div/div[2]/div/div[2]/div/div[1]/div[1]"
            price_element = flight_element.find_element(By.XPATH, price_xpath)
            flight_data['price'] = price_element.text.strip()
            logging.info(f"Found price: {flight_data['price']}")

            # --- Click for Details --- 
            # NOTE: Click is now performed *outside* this function before calling it.
            # Use flight_element directly as the trigger for closing later
            # details_trigger = flight_element # RENAMED for consistency, but it's the flight_element itself
            
            # # Scroll into view before clicking - REMOVED (done outside)
            # self.driver.execute_script("arguments[0].scrollIntoViewIfNeeded(true);", details_trigger) 
            # time.sleep(0.5) # Brief pause after scroll - REMOVED (done outside)
            # details_trigger.click() # Click the element itself - REMOVED (done outside)
            # logging.info("Clicked flight element to open details popup.")
            # time.sleep(3) # Allow time for popup transition and loading - REMOVED (done outside, but maybe keep wait?)
            # Adding a small wait here just in case, though the main wait is outside now
            time.sleep(1)

            # --- Wait for Popup and Extract Details ---
            # Use relative selectors based on class names within the popup container
            popup_container_xpath = "//div[contains(@class, 'o-C7-section')]" # Generic popup container selector
            popup_container_element = self.detail_wait.until(EC.visibility_of_element_located((By.XPATH, popup_container_xpath)))
            logging.info("Details popup appeared and container found.")
            time.sleep(0.5) # Short pause for content rendering within popup

            # Date
            try:
                # date_xpath = "/html/body/div[2]/div/div[1]/div[3]/div/div[2]/div/div[3]/div[2]/div/div[1]/div[2]/div/div[3]/div/div[1]/div/div/div/div[1]/span[1]"
                date_xpath_relative = ".//span[@class='X3K_-header-text']" # Relative XPath
                date_element = popup_container_element.find_element(By.XPATH, date_xpath_relative)
                date_text = date_element.text.replace('Depart •', '').strip() # Keep removal just in case
                flight_data['date'] = date_text
            except NoSuchElementException:
                logging.warning("Could not find date in popup using class X3K_-header-text.")
                flight_data['date'] = "N/A"

            # Flight ID 
            try:
                # flight_time_xpath = "/html/body/div[2]/div/div[1]/div[3]/div/div[2]/div/div[3]/div[2]/div/div[1]/div[2]/div/div[3]/div/div[1]/div/div/div/div[2]/div/div/div[1]/div[3]/div[2]"
                flight_id_xpath_relative = ".//div[contains(@class, 'nAz5-carrier-text')]" # Relative XPath   
                flight_id_element = popup_container_element.find_element(By.XPATH, flight_id_xpath_relative)
                flight_data['flight_id'] = flight_id_element.text.strip()
            except NoSuchElementException:
                logging.warning("Could not find flight id in popup using class nAz5-carrier-text.")
                flight_data['flight_id'] = "N/A"

            # Flight Time (Duration)
            try:
                # flight_time_xpath = "/html/body/div[2]/div/div[1]/div[3]/div/div[2]/div/div[3]/div[2]/div/div[1]/div[2]/div/div[3]/div/div[1]/div/div/div/div[2]/div/div/div[1]/div[3]/div[2]"
                flight_time_xpath_relative = ".//div[contains(@class, 'nAz5-duration-text')]" # Relative XPath
                flight_time_element = popup_container_element.find_element(By.XPATH, flight_time_xpath_relative)
                flight_data['flight_time'] = flight_time_element.text.strip()
            except NoSuchElementException:
                logging.warning("Could not find flight time in popup using class nAz5-duration-text.")
                flight_data['flight_time'] = "N/A"
            
            # Departure/Arrival Blocks (using class g16k)
            flight_data['departure_airport'] = "N/A"
            flight_data['departure_time'] = "N/A"
            flight_data['arrival_airport'] = "N/A"
            flight_data['arrival_time'] = "N/A"
            try:
                departure_arrival_blocks_xpath = ".//div[@class='g16k']" # Exact match for class
                departure_arrival_blocks = popup_container_element.find_elements(By.XPATH, departure_arrival_blocks_xpath)
                
                if len(departure_arrival_blocks) >= 2:
                    logging.info(f"Found {len(departure_arrival_blocks)} departure/arrival blocks (class g16k). Processing first two.")
                    departure_block = departure_arrival_blocks[0]
                    arrival_block = departure_arrival_blocks[1]

                    # Departure Info from first block
                    try:
                        dep_airport_element = departure_block.find_element(By.XPATH, ".//span[contains(@class, 'g16k-station')]")
                        flight_data['departure_airport'] = dep_airport_element.text.strip()
                    except NoSuchElementException:
                        logging.warning("Could not find departure airport in first g16k block.")

                    try:
                        dep_time_element = departure_block.find_element(By.XPATH, ".//span[contains(@class, 'g16k-time')]")
                        flight_data['departure_time'] = dep_time_element.text.strip()
                    except NoSuchElementException:
                        logging.warning("Could not find departure time in first g16k block.")
                    
                    # Arrival Info from second block
                    try:
                        arr_airport_element = arrival_block.find_element(By.XPATH, ".//span[contains(@class, 'g16k-station')]")
                        flight_data['arrival_airport'] = arr_airport_element.text.strip()
                    except NoSuchElementException:
                        logging.warning("Could not find arrival airport in second g16k block.")

                    try:
                        arr_time_element = arrival_block.find_element(By.XPATH, ".//span[contains(@class, 'g16k-time')]")
                        flight_data['arrival_time'] = arr_time_element.text.strip()
                    except NoSuchElementException:
                        logging.warning("Could not find arrival time in second g16k block.")
                        
                else:
                    logging.warning(f"Found {len(departure_arrival_blocks)} blocks with class 'g16k', expected at least 2.")

            except Exception as e:
                logging.error(f"Error processing departure/arrival blocks: {e}")

            # --- Close Popup by clicking the target class --- 
            try:
                logging.info("Attempting to close popup by clicking element with class 'nrc6-inner'...")
                # Find the element globally
                close_target_element = self.detail_wait.until(
                    EC.element_to_be_clickable((By.CLASS_NAME, 'nrc6-inner'))
                )
                # Scroll into view just in case, though overlays are often not scroll-dependent
                # self.driver.execute_script("arguments[0].scrollIntoViewIfNeeded(true);", close_target_element)
                # time.sleep(0.2)
                close_target_element.click()
                logging.info("Clicked element with class 'nrc6-inner'.")
                time.sleep(1) # Allow time for potential close action
            except TimeoutException:
                logging.error("Timeout waiting for element with class 'nrc6-inner' to be clickable.")
            except NoSuchElementException:
                logging.error("Could not find element with class 'nrc6-inner' to click.")
            except Exception as close_click_err:
                logging.error(f"Error clicking element with class 'nrc6-inner': {close_click_err}")

            # --- Explicitly Wait for Popup to Disappear --- 
            # try:
            #     logging.info("Waiting for popup container to become invisible...")
            #     popup_invisible = self.detail_wait.until(
            #         EC.invisibility_of_element_located((By.XPATH, popup_container_xpath))
            #     )
            #     if popup_invisible:
            #         logging.info("Popup container successfully closed.")
            #     else:
            #         # This case might not be reachable if invisibility_of_element_located waits correctly
            #         logging.warning("Popup container did not become invisible within timeout (unexpected state).")
            # except TimeoutException:
            #     logging.error("Popup did NOT close after all attempts within the timeout period.")
            #     # Decide how to handle this - maybe return None to indicate failure?
            #     # For now, we'll log the error and the function will continue, 
            #     # potentially leading to issues on the next iteration. 
            #     # Consider returning None here if the popup MUST be closed.
            #     # return None # <--- Uncomment this to treat failure to close as a data scraping failure

        except (NoSuchElementException, TimeoutException, StaleElementReferenceException) as e:
            logging.error(f"Error processing flight element or its details: {e}")
            # Attempt to close popup if it seems stuck open using the trigger element (less likely to work if initial click failed)
            try:
                if self.driver.find_elements(By.XPATH, "//div[contains(@class, 'dialog-content')]" ):
                     logging.warning("Popup seems stuck open, attempting to click trigger again.")
                     # Use the original details_trigger if available, might cause issues if it's stale
                     # This is a best-effort attempt in an error state
                     try:
                         # Check if the element we originally clicked is still valid/displayed
                         if flight_element and flight_element.is_displayed(): # Check flight_element
                             flight_element.click() # Click flight_element
                             time.sleep(1.5)
                         else:
                             logging.warning("Details trigger (flight_element) not available or displayed for closing attempt.")
                     except Exception as click_err:
                         logging.error(f"Error clicking trigger again to close: {click_err}")
            except Exception as check_err:
                logging.error(f"Error checking for stuck popup: {check_err}")
            return None # Indicate failure for this flight
        except Exception as e:
            logging.error(f"An unexpected error occurred during detail scraping: {e}")
            # self.driver.save_screenshot(f"{self.output_dir}/detail_scrape_error.png")
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
                 # Decide if you want to stop or continue
                 return # Stop if file can't be removed

        # Initialize the file with an empty list
        self.save_results(output_filename)


        logging.info(f"Navigating to: {search_url}")
        self.driver.get(search_url)

        try:
            # --- Handle Potential Overlays (Cookies, etc.) ---
            time.sleep(1) # Initial wait for page load and potential overlays
            # try:
            #     # Example: Check for a common cookie consent button text/ID
            #     cookie_button_xpath = "//button[contains(translate(text(), 'ACCEPT', 'accept'), 'accept') or contains(@id,'accept')]"
            #     cookie_button = WebDriverWait(self.driver, 10).until(
            #         EC.element_to_be_clickable((By.XPATH, cookie_button_xpath))
            #     )
            #     logging.info("Found cookie consent button, clicking it.")
            #     cookie_button.click()
            #     time.sleep(2) # Wait after click
            # except TimeoutException:
            #     logging.info("No cookie consent button found or it timed out.")
            # except Exception as e:
            #     logging.warning(f"Error clicking cookie button: {e}")


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


                            if flight_details:
                                self.scraped_flights.append(flight_details)
                                processed_flight_ids.add(flight_id) # Mark as processed
                                new_flights_found_in_pass = True
                                logging.info(f"Successfully added flight. Total: {len(self.scraped_flights)}")
                                self.save_results(output_filename) # Save incrementally

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
            self.save_results(output_filename) # Final save for this run

    def save_results(self, filename):
        """Saves the currently scraped data to the specified JSON file."""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(self.scraped_flights, f, ensure_ascii=False, indent=2)
            logging.info(f"Saved {len(self.scraped_flights)} flights to {filename}")
        except IOError as e:
            logging.error(f"Error saving data to {filename}: {e}")
        except Exception as e:
            logging.error(f"An unexpected error occurred during saving to {filename}: {e}")

    def close_driver(self):
        """Closes the WebDriver."""
        if self.driver:
            self.driver.quit()
            logging.info("WebDriver closed.")


if __name__ == "__main__":
    DEPARTURE_AIRPORTS = ["HAN", "SGN"]
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
        crawler.close_driver()
        logging.info("Scraping process finished.")
