import requests
import os
from dotenv import load_dotenv
import json

load_dotenv()

def get_geocode_data(address):
    api_key = os.getenv('GOOGLEMAPS_API_KEY')

    if not api_key:
        return "Google Maps API Key not found. Please set the API key in your environment variables."

    params = {
        "address": address,
        "key": api_key
    }

    try:
        response = requests.get("https://maps.googleapis.com/maps/api/geocode/json", params=params)
        response.raise_for_status()  # Raise an exception for HTTP errors
        data = response.json()
        return data['results']
    except requests.exceptions.RequestException as e:
        return f"An error occurred: {e}"
    except KeyError:
        return "Unable to parse response data."
    
if __name__ == "__main__":
    # Ensure GOOGLEMAPS_API_KEY is set
    api_key = os.getenv('GOOGLEMAPS_API_KEY')
    if not api_key:
        print("Error: GOOGLEMAPS_API_KEY environment variable is not set.")
        print("Please set it before running the script (e.g., in a .env file).")
    else:
        file_name = "tripadvisor_da_nang_final_details.json"
        try:
            current_script_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(current_script_dir) 
            json_file_path = os.path.join(project_root, "scrapper", "data", file_name)

            with open(json_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            print(f"Error: The file {json_file_path} was not found.")
            data = [] # Avoid further errors
        except json.JSONDecodeError:
            print(f"Error: Could not decode JSON from {json_file_path}.")
            data = [] # Avoid further errors
        except Exception as e:
            print(f"An unexpected error occurred while reading {json_file_path}: {e}")
            data = []

        if not data:
            print("No data loaded, exiting.")
        else:
            updated_count = 0
            for item in data:
                address = item.get("address")
                if address:
                    print(f"Processing address: {address}")
                    geocode_result = get_geocode_data(address)
                    
                    if isinstance(geocode_result, str): # Error message returned by get_geocode_data
                        print(f"Could not get geocode data for {address}: {geocode_result}")
                        continue

                    if geocode_result and len(geocode_result) > 0:
                        # Assuming the first result is the most relevant one
                        location = geocode_result[0].get("geometry", {}).get("location")
                        if location and "lat" in location and "lng" in location:
                            item["lat"] = str(location["lat"])
                            item["lon"] = str(location["lng"])
                            print(f"Updated lat/lon for {item.get('name', address)} to {item['lat']}, {item['lon']}")
                            updated_count += 1
                        else:
                            print(f"Could not find lat/lon in geocode response for {address}. Response: {geocode_result[0]}")
                    else:
                        print(f"No geocode results for {address}")
                else:
                    print(f"Skipping item due to missing address: {item.get('name', 'Unknown item')}")
            
            if updated_count > 0:
                try:
                    with open(json_file_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    print(f"Successfully updated {updated_count} entries in {json_file_path}")
                except IOError as e:
                    print(f"Error: Could not write updated data to {json_file_path}: {e}")
                except Exception as e:
                    print(f"An unexpected error occurred while writing to {json_file_path}: {e}")
            else:
                print("No entries were updated.")