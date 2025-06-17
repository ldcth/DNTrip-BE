from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time
import json
from collections import deque
import re
import os

class GoogleMapsCrawler:
    def __init__(self):
        opts = Options()
        opts.add_argument("--headless=false")
        self.driver = webdriver.Chrome()
        self.wait = WebDriverWait(self.driver, 10)
        self.start_point = "@{lat},{lon},15z"
        self.initial_URL = "https://www.google.com/maps"
        self.starting_coordinate = [
            "16.0534615_108.2103346", # Da Nang
            # "10.7754483_106.6895788"  # Ho Chi Minh
        ]
        self.keywords = [
    'tourist_attraction', 'restaurant', 'cafe', 'bar',
    'bakery', 'supermarket',
    'shopping_mall', 'store', 'souvenir_store', 'clothing_store', 'campground',
    'museum', 'art_gallery',
    'park', 'zoo', 'aquarium', 'amusement_park', 'stadium',
    'hospital', 'pharmacy', 'atm'
]
        self.current_keyword = ""
        self.list_location_gotten = set()
        self.list_needed_get = deque()

    @staticmethod
    def get_list_view_info(element):
        """Extract information from the list view of a restaurant"""
        info = {}

        try:
            info["name"] = element.find_element(By.CSS_SELECTOR, "div.qBF1Pd").text
        except Exception as e:
            print(e)
            info["name"] = "N/A"

        try:
            info["rating"] = element.find_element(By.CSS_SELECTOR, "span.MW4etd").text
        except Exception as e:
            print(e)
            info["rating"] = "N/A"

        try:
            info["list_rating"] = element.find_element(By.CSS_SELECTOR, "span.UY7F9").text.replace("(", "").replace(")", "")
        except Exception as e:
            print(e)
            info["list_rating"] = "N/A"

        return info

    def get_detail_view_info(self, detail_panel):
        """Extract information from the detail panel of a restaurant"""
        info = {}
        
        try:
            info["description"] = detail_panel.find_element(By.CSS_SELECTOR, "button.DkEaL ").text
        except Exception as e:
            print(e)
            info["description"] = "N/A"
            
        region_element = self.wait.until(EC.presence_of_element_located(
            (By.XPATH, 
             "//div[@class='m6QErb XiKgde ']"
            )))
        info_elements = region_element.find_elements(By.XPATH,
            "//div[@class='RcCsl fVHpi w4vB1d NOE9ve M0S7ae AG25L ']")
        len_info_elements = len(info_elements)
        try:
            info["address"] = region_element.find_element(By.XPATH,
                "(//div[@class='RcCsl fVHpi w4vB1d NOE9ve M0S7ae AG25L '])[1]/button[@class='CsEnBe']").text.replace("\n", "")
        except Exception as e:
            print(e)
            info["address"] = "N/A"
            
        try:
            info["phone"] = region_element.find_element(By.XPATH,
                f"(//div[@class='RcCsl fVHpi w4vB1d NOE9ve M0S7ae AG25L '])[{len_info_elements-1}]/button[@class='CsEnBe']").text.replace("\n", "")
        except Exception as e:
            print(e)
            info["phone"] = "N/A"
            
        # try:
        #     info["plus_code"] = region_element.find_element(By.XPATH,
        #         f"(//div[@class='RcCsl fVHpi w4vB1d NOE9ve M0S7ae AG25L '])[{len_info_elements}]/button[@class='CsEnBe']").text.replace("\n", "")
        # except Exception as e:
        #     print(e)
        #     info["plus_code"] = "N/A"
            
        return info 
    
    def start_crawl(self):
        for keyword in self.keywords:
            self.current_keyword = keyword
            print(f"Starting crawl for: {self.current_keyword}")
            
            # Reset tracking variables for each keyword
            self.list_location_gotten = set()
            self.list_needed_get = deque(self.starting_coordinate)
            
            # Start crawling for this keyword
            self.crawl_keyword()
            
        self.driver.quit()
    
    def crawl_keyword(self):
        places = []
        while self.list_needed_get:
            # Navigate to Google Maps
            latitude, longitude = self.list_needed_get.popleft().split('_')
            print(f"Starting scope for {self.current_keyword}: {latitude}, {longitude}")
            target_URL = self.initial_URL + "/" + self.start_point.format(lat=latitude, lon=longitude) + "?hl=vi"
            self.driver.get(target_URL)
            
            # Search for the current keyword
            search_box = self.wait.until(EC.presence_of_element_located(
                (By.NAME, "q")))
            search_box.send_keys(self.current_keyword)
            search_box.send_keys(Keys.RETURN)
            
            # Wait for results to load
            time.sleep(3)
            
            scrolls = 0
            max_scrolls = 4  # Adjust this number to crawl more results
            processed_elements = set()  # Track which elements we've already processed
            
            while scrolls < max_scrolls:
                print(f"Scroll {scrolls}")
                # Find all place elements
                place_elements = self.wait.until(EC.presence_of_all_elements_located(
                    (By.CSS_SELECTOR, "div.Nv2PK")))

                print(f"Total elements found: {len(place_elements)}")
                
                # Process only new elements that we haven't seen before
                new_elements = []
                for element in place_elements:
                    # Use element ID or some unique attribute to identify elements
                    element_id = element.get_attribute("data-result-index")
                    if not element_id:  # Fallback if data-result-index is not available
                        element_id = element.text[:50]  # Use first 50 chars of text as identifier
                        
                    if element_id not in processed_elements:
                        new_elements.append(element)
                        processed_elements.add(element_id)
                
                print(f"New elements to process: {len(new_elements)}")
                
                # Process each new place in the current view
                for element in new_elements:
                    try:
                        # Get info from list view
                        list_info = self.get_list_view_info(element)
                        print(f"Processing {self.current_keyword}: {list_info['name']}")
                        
                        # Extract coordinates from URL after clicking
                        element.click()
                        time.sleep(2)  # Wait for details panel to load
                        
                        current_url = self.driver.current_url
                        lat = lon = ""
                        try:
                            lat = re.search(r"(?<=!3d)-?[0-9.]+", current_url).group()
                            lon = re.search(r"(?<=!4d)-?[0-9.]+", current_url).group()
                            key = f"{lat}_{lon}"
                            print(key)
                            # Skip if we've already processed this location
                            if key in self.list_location_gotten:
                                print(f"Already processed: {list_info['name']}")
                                time.sleep(1)
                                continue
                                
                            self.list_location_gotten.add(key)
                        except Exception as e:
                            print(f"Could not extract coordinates for: {list_info['name']}")
                            print(e)
                        
                        # Extract detailed information from the side panel
                        detail_panel = self.wait.until(EC.presence_of_element_located(
                            (By.XPATH, "//div[@class='bJzME Hu9e2e tTVLSc']")))
                        
                        # Get info from detail view
                        detail_info = self.get_detail_view_info(detail_panel)
                        
                        # Combine both sets of information
                        place_data = {**list_info, **detail_info}
                        
                        # Add coordinates to the data
                        try:
                            place_data["lat"] = lat
                            place_data["lon"] = lon
                        except Exception as e:
                            print(e)
                            place_data["lat"] = "N/A"
                            place_data["lon"] = "N/A"
                        
                        if place_data not in places:
                            places.append(place_data)
                            print(f"Added {self.current_keyword}: {place_data['name']}")
                        
                        time.sleep(1)  # Wait for list to reload
                    
                    except Exception as e:
                        print(f"Error processing {self.current_keyword}: {str(e)}")
                        time.sleep(1)
                        continue
                
                # Scroll to load more results
                try:
                    # Find the results container and scroll it
                    results_container = self.driver.find_element(By.XPATH, "/html/body/div[1]/div[3]/div[8]/div[9]/div/div/div[1]/div[2]/div/div[1]/div/div/div[1]/div[1]")
                    last_height = self.driver.execute_script("return arguments[0].scrollHeight", results_container)
                    self.driver.execute_script("arguments[0].scrollTo(0, arguments[0].scrollHeight);", results_container)
                    time.sleep(2)
                    
                    # Check if we've reached the end of the scroll
                    new_height = self.driver.execute_script("return arguments[0].scrollHeight", results_container)
                    i = 0
                    while new_height == last_height and i < 3:
                        self.driver.execute_script("arguments[0].scrollTo(0, arguments[0].scrollHeight);", results_container)
                        time.sleep(2)
                        i += 1  # Increment counter
                        # Check if we've reached the end of the scroll
                        new_height = self.driver.execute_script("return arguments[0].scrollHeight", results_container)

                    if new_height == last_height:
                        print("Reached end of results or couldn't scroll further")
                        break
                except Exception as e:
                    print(f"Error scrolling: {str(e)}")
                
                scrolls += 1
            
            print(f"Crawled {len(places)} {self.current_keyword} at location {latitude}, {longitude}")

        # Save all results for this keyword to a single file
        filename = f"{self.current_keyword.replace(' ', '_')}.json"
        
        output_dir = os.path.join("scrapper", "gg")
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, filename)
        
        # Load existing data to avoid overwriting
        all_places_for_keyword = []
        if os.path.exists(output_path):
            try:
                with open(output_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        all_places_for_keyword = data
            except json.JSONDecodeError:
                pass  # File is corrupt or empty, will be overwritten.

        # Create a set of keys from existing places for efficient lookup
        existing_keys = {f"{p.get('lat')}_{p.get('lon')}" for p in all_places_for_keyword}
        
        # Add new, unique places to the list
        for place in places:
            key = f"{place.get('lat')}_{place.get('lon')}"
            if key not in existing_keys:
                all_places_for_keyword.append(place)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(all_places_for_keyword, f, ensure_ascii=False, indent=2)
        
        print(f"Saved {len(all_places_for_keyword)} {self.current_keyword} places to {output_path}")

if __name__ == "__main__":
    crawler = GoogleMapsCrawler()
    crawler.start_crawl()
