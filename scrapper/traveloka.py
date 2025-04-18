import numpy as np
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support import expected_conditions as EC
from time import sleep
import datetime
import pandas as pd
import glob
from selenium.common.exceptions import TimeoutException
import re
import pickle
import os
import dotenv

dotenv.load_dotenv()

class TravelokaCrawler:
    def __init__(self):
        self.driver = None

    def _get_url(self, places):
        urls = []
        today = datetime.datetime.today().date()
        target_date = today + datetime.timedelta(days=2)
        
        for place in places:
            urls.append(
                f"https://www.traveloka.com/vi-vn/flight/fullsearch?ap={place}&dt={target_date.strftime('%d-%m-%Y')}.NA&ps=1.0.0&sc=ECONOMY"
            )
        return urls

    def crawl_plane_trip(self, url_list):
        self.driver = webdriver.Chrome()
        # self.driver = webdriver.Firefox()

        try:
            df_by_url = {}
            # driver = webdriver.Safari()
            # driver.get("http://www.example.com")
            # pickle.dump(driver.get_cookies(), open("cookies.pkl", "wb"))
            # cookies = pickle.load(open("cookies.pkl", "rb"))
            # for cookie in cookies:
            #     print(cookie)
            #     driver.add_cookie(cookie)
            for url in url_list:
                self.driver.get(url)
                sleep(5)
                wait = WebDriverWait(self.driver, 50)
                df = pd.DataFrame(columns=['brand', 'flight_id', 'price',
                                            'start_time', 'start_day',
                                            'end_day', 'end_time',
                                            'trip_time', 'departure', 'arrival'])
                initial_page_length = self.driver.execute_script("return document.body.scrollHeight")
                start_time = []
                end_time = []
                start_day = []
                end_day = []
                trip_time = []
                departure = []
                arrival = []
                price = []
                brand = []
                flight_id = []
                num_steps = 1000000
                scroll_step = initial_page_length // 200

                old_element = []
                for i in range(num_steps):

                    scroll_position = scroll_step * (i + 1)

                    self.driver.execute_script(f"window.scrollTo(0, {scroll_position});")
                    position = self.driver.execute_script("return window.scrollY")
                    new_height = self.driver.execute_script("return document.body.scrollHeight")

                    if scroll_position >= new_height:
                        break
                self.driver.execute_script("window.scrollTo(0, 0)")
                elements = self.driver.find_elements(
                    By.XPATH,
                    "//div[@class='css-1dbjc4n r-9nbb9w r-otx420 r-1i1ao36 r-1x4r79x']"
                    )
                print(len(elements))
                price_elements = wait.until(EC.visibility_of_all_elements_located((
                    By.XPATH, 
                    "//div[@class='css-1dbjc4n r-obd0qt r-eqz5dr r-9aw3ui r-knv0ih r-ggk5by']" \
                    "//h3[@class='css-4rbku5 css-901oao r-a5wbuh r-b88u0q r-rjixqe r-fdjqy7']"
                    )))
                prices_list = [element.text for element in price_elements]
                print(prices_list)

                brand_elements = wait.until(EC.visibility_of_all_elements_located((
                    By.XPATH, 
                    "//div[@class='css-1dbjc4n r-1habvwh r-18u37iz r-1ssbvtb']//" \
                    "div[@class='css-901oao css-cens5h r-a5wbuh r-majxgm r-fdjqy7']"
                    )))
                brands_list = [element.text for element in brand_elements]
                print(brands_list)

                detail = wait.until(EC.visibility_of_all_elements_located((
                    By.XPATH, 
                    "//div[@class='css-1dbjc4n r-1awozwy r-1xr2vsu r-13awgt0 r-18u37iz r-1w6e6rj r-3mtglp r-1x4r79x']" 
                    # "//div[@class='css-1dbjc4n r-1awozwy r-1xr2vsu r-13awgt0 r-18u37iz r-1w6e6rj r-3mtglp r-1x4r79x']" \
                    # "//div[@class='css-1dbjc4n r-1awozwy r-17b9qp5 r-1loqt21 r-1otgn73'][1]" 
                    )))
                print(len(detail))
                print(detail[0].text)
                print(type(detail[0]))
                for i, j in zip(range(len(elements)), detail):
                    if elements[i] in old_element:
                        continue
                    print(123)
                    # button_element = wait.until(EC.visibility_of_element_located((
                    #     By.XPATH, 
                    # "//div[@class='css-1dbjc4n r-1awozwy r-1xr2vsu r-13awgt0 r-18u37iz r-1w6e6rj r-3mtglp r-1x4r79x']//" \
                    # "div[@class='css-1dbjc4n r-1awozwy r-17b9qp5 r-1loqt21 r-1otgn73']"
                    # )))
                    # print(456)
                    # ActionChains(driver).move_to_element(button_element).click().perform()
                    # sleep(1)
                    try:
                        # Wait for element to be clickable
                        # wait.until(EC.element_to_be_clickable(j))
                        # Single click action with ActionChains
                        ActionChains(self.driver).move_to_element(j).click().perform()
                        # Add small delay to let the click action complete
                        sleep(0.5)
                    except TimeoutException:
                        print(f"Element {i} not clickable, skipping...")
                        continue
                    old_element.append(elements[i])
                
                    start_time_elements = wait.until(EC.visibility_of_element_located((
                        By.XPATH, 
                        "//div[@class='css-1dbjc4n r-e8mqni r-1d09ksm r-1h0z5md r-ttb5dx']" \
                        "//div[@class='css-901oao r-a5wbuh r-1b43r93 r-majxgm r-rjixqe r-5oul0u r-fdjqy7']"
                        )))

                    start_time.append(start_time_elements.text)
                    print(start_time_elements.text)
                    end_time_elements = wait.until(EC.visibility_of_element_located((
                        By.XPATH, 
                        "//div[@class='css-1dbjc4n r-e8mqni r-1d09ksm r-1h0z5md r-q3we1 r-ttb5dx']" \
                        "//div[@class='css-901oao r-a5wbuh r-1b43r93 r-majxgm r-rjixqe r-fdjqy7']"
                        )))

                    end_time.append(end_time_elements.text)
                    print(end_time_elements.text)   
                    start_date_elements = wait.until(EC.visibility_of_element_located((
                        By.XPATH, 
                        "//div[@class='css-1dbjc4n r-e8mqni r-1d09ksm r-1h0z5md r-ttb5dx']" \
                        "//div[@class='css-901oao r-a5wbuh r-majxgm r-fdjqy7']"
                        )))
                    start_day.append(start_date_elements.text)
                    print(start_date_elements.text)
                    end_date_elements = wait.until(EC.visibility_of_element_located((
                        By.XPATH, 
                        "//div[@class='css-1dbjc4n r-e8mqni r-1d09ksm r-1h0z5md r-q3we1 r-ttb5dx']" \
                        "//div[@class='css-901oao r-a5wbuh r-majxgm r-fdjqy7']"
                        )))

                    end_day.append(end_date_elements.text)
                    print(end_date_elements.text)
                    trip_time_elements = wait.until(EC.visibility_of_element_located((
                        By.XPATH, 
                        "//div[@class='css-901oao r-13awgt0 r-a5wbuh r-majxgm r-fdjqy7']"
                        )))
                    trip_time.append(trip_time_elements.text)
                    print(trip_time_elements.text)  
                    arrival_elements = wait.until(EC.visibility_of_element_located((
                        By.XPATH,
                        "//div[@class='css-1dbjc4n r-e8mqni r-1habvwh r-13awgt0 r-1h0z5md r-q3we1']" \
                        "//div[@class='css-901oao r-a5wbuh r-1b43r93 r-majxgm r-rjixqe r-fdjqy7']"
                        )))
                    arrival.append(arrival_elements.text)
                    print(arrival_elements.text)
                    departure_elements = wait.until(EC.visibility_of_element_located((
                        By.XPATH, 
                        "//div[@class='css-1dbjc4n r-e8mqni r-1habvwh r-13awgt0 r-1h0z5md']" \
                        "//div[@class='css-901oao r-a5wbuh r-1b43r93 r-majxgm r-rjixqe r-5oul0u r-fdjqy7']"
                        )))
                    departure.append(departure_elements.text)
                    print(departure_elements.text)

                    flight_elements = wait.until(EC.visibility_of_element_located((
                        By.XPATH,
                        "//div[@class='css-1dbjc4n r-13awgt0 r-eqz5dr']" \
                        "//div[@class='css-901oao r-a5wbuh r-1b43r93 r-majxgm r-rjixqe r-14gqq1x r-fdjqy7' and @data-element='flightNumber']"
                        )))
                    flight_id.append(re.sub(r'\•.*', '', flight_elements.text).strip())
                    print(flight_elements.text)
                    print(len(prices_list))
                    price.append(re.sub(r'[^0-9]', '', prices_list[i]))
                    brand.append(brands_list[i])
                    new_df = pd.DataFrame(list(zip(brand, flight_id, price,
                                                    start_time,
                                                    start_day, end_time, end_day,
                                                    trip_time, departure, arrival)),
                                            columns=['brand', 'flight_id', 'price',
                                                    'start_time',
                                                    'start_day', 'end_time', 'end_day',
                                                    'trip_time', 'departure', 'arrival'])

                    df = pd.concat((df, new_df), axis=0, ignore_index=True)
                    start_time = []
                    end_time = []
                    start_day = []
                    end_day = []
                    trip_time = []
                    departure = []
                    arrival = []
                    price = []
                    brand = []
                    flight_id = []
                    j.click()
                    sleep(1)
                new_url = url[53:]
                df.to_csv(f"../data/PlaneTrip_{new_url}.csv", index=False)
                df_by_url[new_url] = df
            return df_by_url
        finally:
            self.driver.quit()

    def preprocessing_data(self, df_by_url):
        process_data = {}
        crawl_date = datetime.datetime.now().strftime('%d-%m-%Y %H:%M')
        
        for url, data in df_by_url.items():
            new_data = data.copy()
            # new_data['price'] = new_data['price'].str.split(' ').str[0].str.replace('.', '').astype('int64')
            new_data['price'] = new_data['price'].str.split(' ').str[0].str.replace('.', '', regex=True).astype('int64')

            new_data['end_day'] = new_data['end_day'].str.split(' ').apply(
                lambda x: f"{x[0]}-{x[2].replace('thg ', '').zfill(2)}" if len(x) > 2 else x[0]
            ) + '-' + str(datetime.datetime.today().year)
            new_data['start_day'] = new_data['start_day'].str.split(' ').apply(
                lambda x: f"{x[0]}-{x[2].replace('thg ', '').zfill(2)}" if len(x) > 2 else x[0]
            ) + '-' + str(datetime.datetime.today().year)

            new_data['crawl_date'] = crawl_date
            new_data['crawl_id'] = url[:7]
            new_data.to_csv(f"../data/PlaneTrip_{url}.csv", index=False)
            process_data[url] = new_data
        return process_data

    def run_crawl_process(self, places):
        url_list = self._get_url(places)
        df_by_url = self.crawl_plane_trip(url_list)
        return self.preprocessing_data(df_by_url)

# Main execution
if __name__ == "__main__":
    places = ['SGN.DAD', 'HAN.DAD']
    crawler = TravelokaCrawler()
    crawler.run_crawl_process(places)
