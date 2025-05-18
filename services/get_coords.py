import googlemaps
import os

API_KEY = os.environ.get("GOOGLEMAPS_API_KEY")

def get_place_coords_if_in_da_nang(place_name: str, api_key: str = API_KEY):
    """
    Checks if a place is in Da Nang and returns its coordinates if found.

    Args:
        place_name (str): The name of the place to search for (e.g., "Fahasa Bookstore").
        api_key (str): Your Google Maps API key.

    Returns:
        dict: A dictionary with "lat" and "lng" if the place is in Da Nang,
              None otherwise.
    """
    if not api_key:
        print("Error: Google Maps API key not found. Please set the GOOGLEMAPS_API_KEY environment variable or pass it as an argument.")
        return None

    gmaps = googlemaps.Client(key=api_key)

    try:
        # Attempt 1: Geocode the place name as is
        # print(f"Attempting to geocode: '{place_name}'")
        geocode_result_attempt1 = gmaps.geocode(place_name)
        # For the first attempt, the query_used_for_api is the place_name itself,
        # and the original_name_to_match is also the place_name.
        place_found_in_da_nang = _parse_geocode_results(
            geocode_results=geocode_result_attempt1, 
            query_used_for_api=place_name, 
            original_name_to_match=place_name, 
            target_city_name="Da Nang"
        )
        if place_found_in_da_nang:
            return place_found_in_da_nang

        # Attempt 2: If not found, try appending ", Da Nang" to the query
        # print(f"'{place_name}' not found in Da Nang on first attempt or no results. Trying with ', Da Nang' suffix.")
        specific_query_for_api = f"{place_name}, Da Nang"
        # print(f"Attempting to geocode: '{specific_query_for_api}'")
        geocode_result_attempt2 = gmaps.geocode(specific_query_for_api)
        
        # For the second attempt, the query_used_for_api is the specific_query_for_api,
        # but the original_name_to_match is still the initial place_name.
        place_found_in_da_nang_specific = _parse_geocode_results(
            geocode_results=geocode_result_attempt2, 
            query_used_for_api=specific_query_for_api, 
            original_name_to_match=place_name, # Important: use original place_name for matching in formatted_address
            target_city_name="Da Nang"
        )
        if place_found_in_da_nang_specific:
            return place_found_in_da_nang_specific

        print(f"'{place_name}' could not be found in Da Nang even after specific search, or the specific place name was not in the address.")
        return None

    except googlemaps.exceptions.ApiError as e:
        print(f"Google Maps API Error: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None

def _parse_geocode_results(geocode_results, query_used_for_api: str, original_name_to_match: str, target_city_name: str):
    """
    Helper function to parse geocode results.
    Checks if the result is in the target city AND if the result reasonably matches the original place name.

    Args:
        geocode_results: The raw results from gmaps.geocode().
        query_used_for_api (str): The actual query string sent to the API for this attempt.
        original_name_to_match (str): The core place name we expect to see in the address or implied by result type.
        target_city_name (str): The city we are targeting (e.g., "Da Nang").

    Returns:
        dict: A dictionary with place details if a valid match is found (e.g. {"name": original_name_to_match, "location": (lat, lng), "description": ..., "type": "custom"}), else None.
    """
    if not geocode_results:
        # print(f"No results from API for query '{query_used_for_api}'.")
        return None

    # Define a list of Google Place types that indicate a specific entity/POI rather than a general area.
    specific_entity_types = [
        'establishment', 'point_of_interest', 'premise', 'street_address',
        'accounting', 'airport', 'amusement_park', 'aquarium', 'art_gallery', 'atm',
        'bakery', 'bank', 'bar', 'beauty_salon', 'bicycle_store', 'book_store',
        'bowling_alley', 'bus_station', 'cafe', 'campground', 'car_dealer',
        'car_rental', 'car_repair', 'car_wash', 'casino', 'cemetery', 'church',
        'city_hall', 'clothing_store', 'convenience_store', 'courthouse', 'dentist',
        'department_store', 'doctor', 'drugstore', 'electrician', 'electronics_store',
        'embassy', 'fire_station', 'florist', 'funeral_home', 'furniture_store',
        'gas_station', 'gym', 'hair_care', 'hardware_store', 'hindu_temple',
        'home_goods_store', 'hospital', 'insurance_agency', 'jewelry_store',
        'laundry', 'lawyer', 'library', 'light_rail_station', 'liquor_store',
        'local_government_office', 'locksmith', 'lodging', 'meal_delivery',
        'meal_takeaway', 'mosque', 'movie_rental', 'movie_theater', 'moving_company',
        'museum', 'night_club', 'painter', 'park', 'parking', 'pet_store', 'pharmacy',
        'physiotherapist', 'plumber', 'police', 'post_office', 'primary_school',
        'real_estate_agency', 'restaurant', 'roofing_contractor', 'rv_park', 'school',
        'secondary_school', 'shoe_store', 'shopping_mall', 'spa', 'stadium', 'storage',
        'store', 'subway_station', 'supermarket', 'synagogue', 'taxi_stand',
        'tourist_attraction', 'train_station', 'transit_station', 'travel_agency',
        'university', 'veterinary_care', 'zoo'
    ]

    for result in geocode_results:
        formatted_address = result.get('formatted_address', '')
        address_components = result.get('address_components', [])
        result_types = result.get('types', [])
        location = result.get('geometry', {}).get('location')

        if not location:
            continue # Skip if no coordinates

        is_in_target_city = False
        city_name_found = ""
        for component in address_components:
            comp_long_name = component.get('long_name', '')
            comp_short_name = component.get('short_name', '')
            comp_types = component.get('types', [])

            if 'locality' in comp_types and (target_city_name in comp_long_name or target_city_name in comp_short_name):
                is_in_target_city = True
                city_name_found = comp_long_name
                break
            if ('administrative_area_level_1' in comp_types or 'administrative_area_level_2' in comp_types) and \
               (("Đà Nẵng" in comp_long_name or target_city_name in comp_long_name) or \
                ("Đà Nẵng" in comp_short_name or target_city_name in comp_short_name)):
                is_in_target_city = True
                city_name_found = comp_long_name
                break
        
        if is_in_target_city:
            # Case 1: If the original query was for the target city itself (e.g., place_name="Da Nang")
            # This function is for finding specific POIs *within* Da Nang, not Da Nang itself.
            if original_name_to_match.lower() == target_city_name.lower():
                # print(f"DEBUG: Query for target city itself ('{original_name_to_match}') - not returning as custom POI. Query: '{query_used_for_api}'.")
                return None 

            # Case 2: The query was for a specific place within the target city
            is_specific_entity_type = any(t in result_types for t in specific_entity_types)

            if is_specific_entity_type:
                # If Google returns a result with a specific entity type, assume it's a valid POI.
                # print(f"DEBUG: Matched specific entity type. Place: {original_name_to_match}, Address: {formatted_address}, Types: {result_types}, Query: {query_used_for_api}")
                print(f"Found '{formatted_address}' in {city_name_found} (API query: '{query_used_for_api}'). Matched as specific entity type.")
                return {
                    "name": original_name_to_match,
                    "location": (location.get('lat'), location.get('lng')),
                    "description": f"User specified stop: {original_name_to_match} (verified in Da Nang via specific type match)",
                    "type": "custom_verified" 
                }
            else:
                # If the result type is generic, require the name to be in the formatted address.
                if original_name_to_match.lower() in formatted_address.lower():
                    # print(f"DEBUG: Matched generic type with name in address. Place: {original_name_to_match}, Address: {formatted_address}, Types: {result_types}, Query: {query_used_for_api}")
                    print(f"Found '{formatted_address}' in {city_name_found} (API query: '{query_used_for_api}'). Matched by name in generic address.")
                    return {
                        "name": original_name_to_match,
                        "location": (location.get('lat'), location.get('lng')),
                        "description": f"User specified stop: {original_name_to_match} (verified in Da Nang, name matched in address)",
                        "type": "custom_verified" 
                    }
                # else:
                    # print(f"DEBUG: Discarding generic type, name '{original_name_to_match}' not in address '{formatted_address}'. Types: {result_types}, Query: '{query_used_for_api}'")

    # print(f"Query '{query_used_for_api}' did not yield a confirmed result for '{original_name_to_match}' in {target_city_name}.")
    return None

if __name__ == '__main__':
    if not API_KEY:
        print("Please set the GOOGLEMAPS_API_KEY environment variable to run the example.")
        print("Example: export GOOGLEMAPS_API_KEY='your_api_key_here'")
    else:
        place1 = "Fahasa Bookstore"
        coords1 = get_place_coords_if_in_da_nang(place1)
        if coords1:
            print(f"Coordinates for {place1} in Da Nang: {coords1}")
        else:
            print(f"Could not find {place1} in Da Nang.")

        print("\n" + "="*20 + "\n")

        place2 = "Eiffel Tower"
        coords2 = get_place_coords_if_in_da_nang(place2)
        if coords2:
            print(f"Coordinates for {place2} in Da Nang: {coords2}")
        else:
            print(f"Could not find {place2} in Da Nang (as expected).")

        print("\n" + "="*20 + "\n")
        
        place3 = "Ezi" # A known place in Da Nang
        coords3 = get_place_coords_if_in_da_nang(place3)
        if coords3:
            print(f"Coordinates for {place3} in Da Nang: {coords3}")
        else:
            print(f"Could not find {place3} in Da Nang.")

        print("\n" + "="*20 + "\n")

        place4 = "Cloudy" # Another known place in Da Nang
        coords4 = get_place_coords_if_in_da_nang(place4)
        if coords4:
            print(f"Coordinates for {place4} in Da Nang: {coords4}")
        else:
            print(f"Could not find {place4} in Da Nang.")
