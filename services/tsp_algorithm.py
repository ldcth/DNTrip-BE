import numpy as np
import re
import json
import random
import math # Import math for Haversine
from services.get_coords import get_place_coords_if_in_da_nang # Added Import

HOTEL_DATA_FILE = "scrapper/data/tripadvisor_da_nang_final_details.json"
RESTAURANT_DATA_FILE = "scrapper/data/restaurants.json"
MUST_VISIT_DATA_FILE = "scrapper/data/must.json"

# --- Helper functions to load data ---
def get_location_hotel():
    """Reads hotel data, selects one randomly, and returns its info."""
    try:
        with open(HOTEL_DATA_FILE, "r", encoding='utf-8') as f:
            hotels = json.load(f)
        if not hotels:
            return []
        selected_hotel = random.choice(hotels)
        # Convert lat/lon to float
        lat = float(selected_hotel.get("lat", 0.0))
        lon = float(selected_hotel.get("lon", 0.0))
        hotel_name_for_desc = selected_hotel.get("name", "Unknown Hotel")
        return [{
            "place": hotel_name_for_desc,
            "location": (lat, lon),
            "description": selected_hotel.get("description", f"Accommodation: {hotel_name_for_desc}")
        }]
    except FileNotFoundError:
        print("Error: hotels.json not found.")
        return []
    except json.JSONDecodeError:
        print("Error: Could not decode hotels.json.")
        return []
    except Exception as e:
        print(f"An error occurred in get_location_hotel: {e}")
        return []

def get_restaurants():
    """Reads restaurant data and returns info for all."""
    try:
        with open(RESTAURANT_DATA_FILE, "r", encoding='utf-8') as f:
            restaurants_data = json.load(f)
        restaurants_list = []
        for r in restaurants_data:
            try:
                lat = float(r.get("lat", 0.0))
                lon = float(r.get("lon", 0.0))
                name = r.get("name", "Unknown Restaurant") # Get name for fallback description
                description = r.get("description", f"Enjoy a meal at {name}") # Read description, with a fallback
                restaurants_list.append({
                    "place": name,
                    "location": (lat, lon),
                    "description": description # Store the description
                    # Add other fields if needed
                })
            except (ValueError, TypeError):
                print(f"Warning: Skipping restaurant due to invalid coordinates: {r.get('name')}")
                continue
        return restaurants_list
    except FileNotFoundError:
        print("Error: restaurants.json not found.")
        return []
    except json.JSONDecodeError:
        print("Error: Could not decode restaurants.json.")
        return []
    except Exception as e:
        print(f"An error occurred in get_restaurants: {e}")
        return []

def get_must_visit_places():
    """Reads must-visit places data and returns info for all."""
    try:
        with open(MUST_VISIT_DATA_FILE, "r", encoding='utf-8') as f:
            places_data = json.load(f)
        places_list = []
        for p in places_data:
            try:
                lat = float(p.get("lat", 0.0))
                lon = float(p.get("lon", 0.0))
                priority = int(p.get("priority", 99))
                description = p.get("description", "")
                # Process time_to_visit into a list/set for easier checking
                time_str = p.get("time_to_visit", "").lower()
                times = {t.strip() for t in time_str.split(',') if t.strip()}
                
                places_list.append({
                    "place": p.get("name", "Unknown Place"),
                    "location": (lat, lon),
                    "priority": priority,
                    "times": times,
                    "description": description
                })
            except (ValueError, TypeError):
                print(f"Warning: Skipping place due to invalid coordinates or priority: {p.get('name')}")
                continue
        return places_list
    except FileNotFoundError:
        print("Error: must.json not found.")
        return []
    except json.JSONDecodeError:
        print("Error: Could not decode must.json.")
        return []
    except Exception as e:
        print(f"An error occurred in get_must_visit_places: {e}")
        return []

# Get detail adress from web searchsearch


def process_travel_duration(travel_duration):
    if type(travel_duration) == int:
      return travel_duration
    else:
      input_str = travel_duration.lower()
      days = 0

      match = re.match(r"(\d+)\s*ngày\s*(\d+)?\s*đêm?", input_str)
      if match:
          days = int(match.group(1))
          return days

      match = re.match(r"(\d+)\s*days?\s*(\d+)?\s*nights?", input_str)
      if match:
          days = int(match.group(1))
          return days

      match = re.match(r"(\d+)\s*ngày?", input_str)
      if match:
          days = int(match.group(1))
          return days

      match = re.match(r"(\d+)\s*days?", input_str)
      if match:
          days = int(match.group(1))
          return days

      match = re.match(r"(\d+)\s*weeks?", input_str)
      if match:
          days = int(match.group(1)) * 7
          return days

# --- Distance Calculation ---

def haversine(coord1, coord2):
    """Calculate the Haversine distance between two points (latitude, longitude) in kilometers."""
    R = 6371  # Earth radius in kilometers
    
    # Ensure coords are tuples of floats
    try:
        lat1_f, lon1_f = map(float, coord1)
        lat2_f, lon2_f = map(float, coord2)
    except (ValueError, TypeError):
        print(f"Error: Invalid coordinates format for Haversine calculation: {coord1}, {coord2}")
        # For user-specified stops with no valid coordinates, this might return inf.
        # The impact is that they might seem very far if not handled before routing.
        return float('inf') 

    lat1, lon1 = map(math.radians, (lat1_f, lon1_f))
    lat2, lon2 = map(math.radians, (lat2_f, lon2_f))

    dlon = lon2 - lon1
    dlat = lat2 - lat1

    a = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    distance = R * c
    return distance

def euclidean(point1, point2):
    """Calculate the Euclidean distance between two points."""
    return np.sqrt(np.sum((np.array(point1) - np.array(point2)) ** 2))

# --- Place/Restaurant Selection Helpers ---
def select_places(places_list, time_of_day, count=1, already_selected_names_lower=None):
    """Selects places based on time_of_day, biasing towards priority 1, ensuring uniqueness (case-insensitive)."""
    if already_selected_names_lower is None:
        already_selected_names_lower = set()

    # Filter by time_of_day and names not already selected (case-insensitive)
    eligible_places = [
        p for p in places_list 
        if time_of_day in p.get('times', set()) and p.get('place', '').lower() not in already_selected_names_lower
    ]
    
    if not eligible_places:
        return []

    # --- Weighted Selection Logic for DISTINCT items --- 
    priority_weight = 3 # Higher chance for priority 1
    other_weight = 1    # Lower chance for others

    num_available = len(eligible_places)
    num_to_select = min(count, num_available)
    
    if num_to_select == 0:
        return []

    selected_details = []
    # Create a temporary list of eligible places for iterative selection
    # This copy is needed so we can remove items from it
    current_eligible_for_sampling = list(eligible_places) 
    
    for _ in range(num_to_select):
        if not current_eligible_for_sampling:
            break # No more unique items to select

        # Calculate weights for the *currently available* items for this iteration
        current_weights = [priority_weight if p.get('priority') == 1 else other_weight for p in current_eligible_for_sampling]
        
        if not current_weights: # Should not happen if current_eligible_for_sampling is not empty
            break

        # Perform a single weighted choice
        chosen_item = random.choices(current_eligible_for_sampling, weights=current_weights, k=1)[0]
        selected_details.append(chosen_item)
        
        # Remove the chosen item from the list for subsequent selections to ensure uniqueness
        # This works because chosen_item is a reference to an element in current_eligible_for_sampling
        current_eligible_for_sampling.remove(chosen_item)

    return selected_details

def select_restaurants(restaurants_list, count=1, already_selected_names_lower=None):
    """Selects random restaurants, ensuring uniqueness (case-insensitive)."""
    if already_selected_names_lower is None:
        already_selected_names_lower = set()

    # Filter out restaurants already selected (case-insensitive)
    eligible_restaurants = [
        r for r in restaurants_list 
        if r.get('place', '').lower() not in already_selected_names_lower
    ]

    if not eligible_restaurants or count <= 0:
        return []
        
    actual_count = min(count, len(eligible_restaurants))
    return random.sample(eligible_restaurants, actual_count)

# --- Helper for User Specified Stops ---
def find_or_create_place_details(stop_spec, must_visit_places_list, all_restaurants_list):
    """
    Tries to find the specified place in must_visit_places or restaurants.
    If not found, uses get_place_coords_if_in_da_nang to verify and get details.
    stop_spec is a dict like {'name': ..., 'day': ..., 'time_of_day': ..., 'address': ..., 'location': (lat,lon) or None, 'original_description': ..., 'original_type': ...}
    The 'location' field in stop_spec is (lat, lon) if present and pre-verified.
    Returns a place-like dictionary if valid and in Da Nang, or an error dict if not.
    """
    place_name = stop_spec['name']
    time_of_day = stop_spec.get('time_of_day', '').lower() # Added .get for safety
    original_description = stop_spec.get('original_description')
    original_type = stop_spec.get('original_type')

    # First, try to match with must_visit_places or restaurants using name, prioritizing these lists.
    for p in must_visit_places_list:
        if p['place'].lower() == place_name.lower():
            place_detail = p.copy()
            # If stop_spec had an original_type that is more specific (e.g. user changed a place to be a restaurant for a meal slot)
            # allow it to override if the original type was generic 'place'
            if original_type and original_type != 'place': # and place_detail.get('type', 'place') == 'place': <--- this condition might be too restrictive
                 place_detail['type'] = original_type
            else:
                place_detail.setdefault('type', 'place')
            # Ensure description is present, using original from dataset if available
            place_detail.setdefault('description', 'Description not available.') # Fallback
            return place_detail

    for r in all_restaurants_list:
        if r['place'].lower() == place_name.lower():
            restaurant_detail = r.copy()
            restaurant_detail.setdefault('type', 'restaurant')
            restaurant_detail['times'] = {time_of_day} if time_of_day else restaurant_detail.get('times', set()) # Preserve existing times if any
            restaurant_detail.setdefault('priority', 1) 
            restaurant_detail.setdefault('description', 'Restaurant description not available.') # Fallback
            return restaurant_detail

    # If not found in local lists, then proceed with geocoding or using pre-specified coords
    # Check if location is already provided and valid in stop_spec (e.g., from user's tool input or preserved plan)
    if 'location' in stop_spec and isinstance(stop_spec['location'], (list, tuple)) and len(stop_spec['location']) == 2:
        try:
            lat, lon = float(stop_spec['location'][0]), float(stop_spec['location'][1])
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                print(f"Using pre-specified/preserved coordinates for '{place_name}': ({lat}, {lon})")
                # Use original_description if available (from preserved plan), else generate one.
                description_to_use = original_description if original_description else f"User-specified visit: {place_name}"
                if not original_description and stop_spec.get('address'): # Add address only if desc was auto-generated
                    description_to_use += f" at {stop_spec['address']}"
                
                return {
                    "place": place_name,
                    "location": (lat, lon),
                    "priority": stop_spec.get('priority', 0),  # Preserve priority if passed, else default for custom
                    "times": {time_of_day} if time_of_day else set(),
                    "description": description_to_use,
                    "type": original_type if original_type else "custom_pre_geocoded"
                }
            else:
                print(f"Warning: Pre-specified coordinates for '{place_name}' ({stop_spec['location']}) are out of valid range. Will attempt geocoding via API.")
        except (TypeError, ValueError):
            print(f"Warning: Invalid format for pre-specified coordinates for '{place_name}': {stop_spec['location']}. Will attempt geocoding via API.")

    # If not found in local data AND no valid pre-specified coords, try to geocode using get_coords service
    print(f"Place '{place_name}' not found in local data or pre-specified coords were invalid. Attempting to verify with Google Maps API via get_coords...")
    verified_place_data = get_place_coords_if_in_da_nang(place_name) 

    if verified_place_data and isinstance(verified_place_data.get('location'), (list, tuple)):
        print(f"Successfully verified and geocoded '{place_name}' in Da Nang: {verified_place_data['location']}")
        return {
            "place": verified_place_data['name'], 
            "location": tuple(verified_place_data['location']),
            "priority": 0, 
            "times": {time_of_day} if time_of_day else set(),
            "description": verified_place_data.get('description', f"User-specified visit: {place_name}"),
            "type": verified_place_data.get('type', "custom_verified")
        }
    else:
        print(f"Could not verify '{place_name}' in Da Nang using get_coords. It might not exist or is not in Da Nang.")
        return {"error": "not_in_da_nang", "name": place_name, "address": stop_spec.get('address')}


def optimize_distance_tour(travel_duration_str, user_specified_stops_for_modification=None, previous_base_plan_data=None):
    travel_duration_days = process_travel_duration(travel_duration_str)
    if travel_duration_days is None or travel_duration_days <= 0:
        return {"plan": None, "message": "Invalid travel duration provided."}

    # --- Caching for find_or_create_place_details ---
    place_details_cache = {}

    def get_cached_place_details(spec, must_visit_list, restaurant_list):
        cache_key = spec['name'].lower() # Assuming name is the primary identifier for caching
        if cache_key in place_details_cache:
            # print(f"DEBUG: Cache hit for {cache_key}")
            return place_details_cache[cache_key]
        
        # print(f"DEBUG: Cache miss for {cache_key}, calling find_or_create_place_details")
        details = find_or_create_place_details(spec, must_visit_list, restaurant_list)
        place_details_cache[cache_key] = details
        return details
    # --- End Caching ---

    # --- 1. Load Data & Hotel Setup ---
    location_hotel_list = get_location_hotel()
    if not location_hotel_list:
        return {"plan": None, "message": "Itinerary generation failed: No hotel data could be loaded."}
    
    hotel_name = None
    hotel_coords = None
    hotel_description = "Default hotel description."

    if previous_base_plan_data and isinstance(previous_base_plan_data.get('hotel'), dict):
        prev_hotel = previous_base_plan_data['hotel']
        if prev_hotel.get('name') and isinstance(prev_hotel.get('coords'), list) and len(prev_hotel['coords']) == 2:
            try:
                hotel_name = prev_hotel['name']
                hotel_coords = (float(prev_hotel['coords'][0]), float(prev_hotel['coords'][1]))
                hotel_description = prev_hotel.get('description', f"Accommodation: {hotel_name}")
                print(f"Using hotel from previous plan: {hotel_name} at {hotel_coords}")
            except ValueError:
                print("Warning: Could not parse coordinates from previous hotel. Selecting a new one.")
                hotel_coords = None # Fallback to selecting new hotel
        else:
            print("Warning: Previous hotel data incomplete. Selecting a new one.")
    
    if not hotel_coords: # If no previous hotel or previous hotel data was bad
        selected_hotel_info = location_hotel_list[0] # get_location_hotel already randomizes if multiple
        hotel_name = selected_hotel_info["place"]
        hotel_coords = tuple(selected_hotel_info["location"]) # Ensure it's a tuple
        hotel_description = selected_hotel_info.get("description", f"Accommodation: {hotel_name}")
        print(f"Selected New Hotel: {hotel_name} at {hotel_coords}")


    must_visit_places = get_must_visit_places()
    restaurants = get_restaurants()

    modification_stops_map = {}
    # Before building the plan, validate all user_specified_stops
    if user_specified_stops_for_modification:
        for stop_item_spec_idx, stop_item_spec in enumerate(user_specified_stops_for_modification):
            if not isinstance(stop_item_spec, dict):
                print(f"Warning: Invalid stop specification at index {stop_item_spec_idx}: {stop_item_spec}. Skipping.")
                continue
                if not all(k in stop_item_spec for k in ['name', 'day', 'time_of_day']):
                     print(f"Warning: Invalid stop specification (missing keys) at index {stop_item_spec_idx}: {stop_item_spec}. Skipping this stop for validation.")
                     continue

            # Use the caching wrapper for validation
            place_detail_for_validation = get_cached_place_details(stop_item_spec, must_visit_places, restaurants)
            if isinstance(place_detail_for_validation, dict) and place_detail_for_validation.get("error") == "not_in_da_nang":
                problematic_stop_name = place_detail_for_validation.get("name", "Unknown place")
                error_message = f"The specified stop '{problematic_stop_name}' is not located in Da Nang or could not be verified."
                if previous_base_plan_data: # Modify mode
                    print(f"Validation failed (modify mode): {error_message}")
                    return {"plan": previous_base_plan_data, "message": f"Cannot modify plan. I tried to alter your plan, but unfortunately, {error_message}"}
                else: # Create mode
                    print(f"Validation failed (create mode): {error_message}")
                    return {"plan": None, "message": f"Cannot create plan. I tried to create your plan, but unfortunately, {error_message}"}    
            
            # If valid, add to modification_stops_map (original logic for mapping)
            try:
                day_key = int(stop_item_spec['day'])
                time_key = stop_item_spec['time_of_day'].lower()
                map_key = (day_key, time_key)
                modification_stops_map.setdefault(map_key, []).append(stop_item_spec) # Store the original spec
            except (KeyError, ValueError, TypeError) as e:
                print(f"Warning: Skipping invalid user_specified_stop (item #{stop_item_spec_idx}: {stop_item_spec}) for map due to error: {e}")
                # This stop was already validated for location, error here is about day/time format
                continue


    selected_places_ever = set() 

    itinerary_result = {
        "hotel": {"name": hotel_name, "coords": list(hotel_coords), "description": hotel_description},
        "daily_plans": []
    }
    
    NUM_CANDIDATES_PLACE = 3       
    NUM_CANDIDATES_EVENING = 3     
    NUM_CANDIDATES_RESTAURANT = 3  
    MAX_EVENING_STOPS = 2          
    
    for day_index in range(travel_duration_days):
        current_day_number = day_index + 1
        print(f"DEBUG: --- Starting Day {current_day_number} of {travel_duration_days} ---")
        
        day_data = {
            "day": current_day_number,
            "planned_stops": {}, 
            "route": []          
        }
        
        current_location_for_day = hotel_coords 
        step_counter = 0

        day_data["route"].append({
            "step": step_counter,
            "time_slot": "StartOfDay", 
            "type": "hotel",
            "name": hotel_name,
            "coords": list(hotel_coords),
            "distance_from_previous_km": 0.0,
            "description": hotel_description
        })

        time_slots_of_day = ['morning', 'lunch', 'afternoon', 'dinner', 'evening']

        for time_slot_lower in time_slots_of_day:
            time_slot_capitalized = time_slot_lower.capitalize()
            day_data["planned_stops"].setdefault(time_slot_capitalized, []) 
            current_slot_key = (current_day_number, time_slot_lower)
            
            chosen_stops_details_for_slot = [] 

            if current_slot_key in modification_stops_map:
                print(f"DEBUG: Day {current_day_number} {time_slot_capitalized} - Applying MODIFICATION.")
                user_modification_stop_specs = modification_stops_map[current_slot_key]
                for stop_spec_dict in user_modification_stop_specs:
                    # Use the caching wrapper when processing modifications
                    place_detail = get_cached_place_details(stop_spec_dict, must_visit_places, restaurants)
                    
                    if isinstance(place_detail, dict) and place_detail.get("error"):
                        problem_name = place_detail.get('name', 'Unknown problem place')
                        error_msg_runtime = f"Error processing stop '{problem_name}' for Day {current_day_number}, {time_slot_capitalized}: Not in Da Nang or invalid."
                        print(f"RUNTIME ERROR: {error_msg_runtime}")
                        if previous_base_plan_data:
                            return {"plan": previous_base_plan_data, "message": f"Failed to apply modification. {error_msg_runtime}"}
                        else:
                            return {"plan": None, "message": f"Failed to create plan. {error_msg_runtime}"}

                    if time_slot_lower in ['lunch', 'dinner'] and place_detail.get('type') not in ['restaurant', 'custom_verified', 'custom_pre_geocoded']: # Allow custom to be food if in food slot
                        place_detail['type'] = 'restaurant' # Coerce if it's a generic place in a meal slot
                    
                    chosen_stops_details_for_slot.append(place_detail)
                    if isinstance(place_detail.get('place'), str):
                        selected_places_ever.add(place_detail['place'].lower())
            
            elif previous_base_plan_data:
                prev_day_plan_data = next((dp for dp in previous_base_plan_data.get('daily_plans', []) if dp.get('day') == current_day_number), None)
                if prev_day_plan_data and isinstance(prev_day_plan_data.get('planned_stops'), dict):
                    prev_slot_name_found = next((k for k in prev_day_plan_data['planned_stops'] if k.lower() == time_slot_lower), None)
                    if prev_slot_name_found and prev_day_plan_data['planned_stops'].get(prev_slot_name_found):
                        preserved_place_names = prev_day_plan_data['planned_stops'][prev_slot_name_found]
                        print(f"DEBUG: Day {current_day_number} {time_slot_capitalized} - Preserving from PREVIOUS: {preserved_place_names}")

                        # --- Optimization: Create a map of previous route details for faster lookup ---
                        previous_route_details_map = {}
                        if prev_day_plan_data.get('route'):
                            for r_stop in prev_day_plan_data['route']:
                                # Key by (name_lower, time_slot_lower) for uniqueness within a day's route for a specific slot context
                                # Note: This assumes a place name is unique for a given time_slot in the previous route.
                                # If a place could appear multiple times in the same slot in the route (unlikely), this takes the last one.
                                if r_stop.get('name') and r_stop.get('time_slot'): # Ensure keys exist
                                    map_key = (r_stop['name'].lower(), r_stop['time_slot'].lower())
                                    previous_route_details_map[map_key] = r_stop
                        # --- End Optimization ---

                        for place_name in preserved_place_names:
                            if place_name.lower() not in selected_places_ever: 
                                mock_stop_spec = {'name': place_name, 'day': current_day_number, 'time_of_day': time_slot_lower}
                                
                                # --- Use the optimized map lookup ---
                                prev_route_stop_details = previous_route_details_map.get((place_name.lower(), time_slot_lower))
                                if prev_route_stop_details:
                                    if isinstance(prev_route_stop_details.get('coords'), list) and len(prev_route_stop_details['coords']) == 2:
                                        mock_stop_spec['location'] = tuple(prev_route_stop_details['coords'])
                                    if prev_route_stop_details.get('description'):
                                        mock_stop_spec['original_description'] = prev_route_stop_details['description']
                                    if prev_route_stop_details.get('type'):
                                        mock_stop_spec['original_type'] = prev_route_stop_details['type']
                                # --- End Use Optimized Map ---
                                
                                # Use the caching wrapper
                                place_detail = get_cached_place_details(mock_stop_spec, must_visit_places, restaurants)
                                if isinstance(place_detail, dict) and place_detail.get("error"):
                                    problem_name = place_detail.get('name', 'Unknown problem place')
                                    print(f"Warning: Preserved stop '{problem_name}' from previous plan is now considered invalid. Skipping.")
                                    continue # Skip this problematic preserved stop

                                if time_slot_lower in ['lunch', 'dinner'] and place_detail.get('type') not in ['restaurant', 'custom_verified', 'custom_pre_geocoded']:
                                    place_detail['type'] = 'restaurant'
                                chosen_stops_details_for_slot.append(place_detail)
                                if isinstance(place_detail.get('place'), str):
                                    selected_places_ever.add(place_detail['place'].lower())
            
            if not chosen_stops_details_for_slot: # Auto-select
                print(f"DEBUG: Day {current_day_number} {time_slot_capitalized} - Slot empty, AUTO-SELECTING.")
                num_stops_to_pick = 1
                candidate_pool = []

                if time_slot_lower == 'lunch' or time_slot_lower == 'dinner':
                    candidate_pool = select_restaurants(restaurants, NUM_CANDIDATES_RESTAURANT, selected_places_ever)
                elif time_slot_lower == 'evening':
                    num_stops_to_pick = random.randint(1, MAX_EVENING_STOPS) 
                    candidate_pool = select_places(must_visit_places, time_slot_lower, NUM_CANDIDATES_EVENING, selected_places_ever)
                else: # Morning, Afternoon
                    candidate_pool = select_places(must_visit_places, time_slot_lower, NUM_CANDIDATES_PLACE, selected_places_ever)
                
                # Log candidate pool for debugging auto-selection
                # print(f"DEBUG:   Fetched {len(candidate_pool)} candidates for {time_slot_capitalized} ({num_stops_to_pick} stop(s) to pick): {[c.get('place') for c in candidate_pool]}")

                temp_current_loc_for_multi_stop_slot = current_location_for_day 
                
                for i in range(num_stops_to_pick):
                    if not candidate_pool:
                        # print(f"DEBUG:   Stop {i+1} for {time_slot_capitalized}: Ran out of candidates.")
                        break
                    best_candidate_for_stop = None
                    if time_slot_lower == 'morning': # Random for morning
                        best_candidate_for_stop = random.choice(candidate_pool)
                    else: # Greedy distance-based for others
                        min_dist = float('inf')
                        ref_loc = temp_current_loc_for_multi_stop_slot if i > 0 and chosen_stops_details_for_slot else current_location_for_day
                        for candidate in candidate_pool:
                            try:
                                cand_coords_raw = candidate["location"]
                                cand_coords = (float(cand_coords_raw[0]), float(cand_coords_raw[1]))
                                dist = haversine(ref_loc, cand_coords)
                                if dist < min_dist:
                                    min_dist = dist
                                    best_candidate_for_stop = candidate
                            except (TypeError, ValueError, IndexError, KeyError): # Added KeyError
                                print(f"Warning: Invalid coordinates/structure for auto-select candidate {candidate.get('place') if isinstance(candidate,dict) else 'UnknownCandidate'}. Skipping.")
                                continue
                    
                    if best_candidate_for_stop:
                        chosen_stops_details_for_slot.append(best_candidate_for_stop)
                        if isinstance(best_candidate_for_stop.get('place'), str):
                             selected_places_ever.add(best_candidate_for_stop['place'].lower())
                        candidate_pool.remove(best_candidate_for_stop) 
                        try:
                            temp_current_loc_for_multi_stop_slot = (float(best_candidate_for_stop["location"][0]), float(best_candidate_for_stop["location"][1]))
                        except (TypeError, ValueError, IndexError, KeyError): # Added KeyError
                             print(f"Warning: Could not update temp_current_loc_for_multi_stop_slot for {best_candidate_for_stop.get('place') if isinstance(best_candidate_for_stop,dict) else 'UnknownStop'}")
                    else:
                        # print(f"DEBUG:   Stop {i+1} for {time_slot_capitalized}: No suitable candidate found from remaining.")
                        break 
            
            for stop_detail in chosen_stops_details_for_slot:
                step_counter += 1
                try:
                    stop_coords_raw = stop_detail["location"]
                    stop_coords = (float(stop_coords_raw[0]), float(stop_coords_raw[1]))
                except (TypeError, ValueError, IndexError, KeyError): # Added KeyError
                    print(f"Warning RouteGen: Invalid coords/structure for {stop_detail.get('place') if isinstance(stop_detail,dict) else 'UnknownStopInRoute'}. Using (0,0). Detail was: {stop_detail}")
                    stop_coords = (0.0, 0.0)
                
                stop_name = stop_detail.get("place", "Unknown Stop") # Use .get for safety
                distance_km = haversine(current_location_for_day, stop_coords)
                
                stop_type = stop_detail.get("type", "place")
                if time_slot_lower in ['lunch', 'dinner'] and stop_type not in ['restaurant', 'custom_verified', 'custom_pre_geocoded']:
                    stop_type = "restaurant"

                route_stop_data = {
                    "step": step_counter,
                    "time_slot": time_slot_capitalized,
                    "name": stop_name,
                    "type": stop_type,
                    "coords": list(stop_coords),
                    "distance_from_previous_km": round(distance_km, 2),
                    "description": stop_detail.get("description", f"Visit to {stop_name}")
                }
                day_data["route"].append(route_stop_data)
                day_data["planned_stops"][time_slot_capitalized].append(stop_name)
                current_location_for_day = stop_coords 

        itinerary_result["daily_plans"].append(day_data)
    
    success_message = "Here is the suggested itinerary for you. Tell me if you want any changes!"
    if user_specified_stops_for_modification and previous_base_plan_data:
        success_message = "Here is the updated itinerary for you. Tell me if you want any changes!"
    elif user_specified_stops_for_modification:
        success_message = "Here is the itinerary for you based on your requests. Tell me if you want any changes!"

    return {"plan": itinerary_result, "message": success_message}


# --- Test function ---
def test_optimize_distance_tour():
    print("Testing itinerary generation for '3 days 2 nights'...")
    full_plan_no_specific = optimize_distance_tour('2 days') 
    print("\n--- Generated Itinerary Data (No Specific Stops) ---")
    print(json.dumps(full_plan_no_specific, indent=2, ensure_ascii=False))

    print("\n\nTesting itinerary generation for '2 days' WITH specific stops...")
    specific_stops_test = [
        {'name': 'Ba Na Hills', 'day': 1, 'time_of_day': 'morning', 'address': None, 'location': (15.995363, 107.996182)}, # Known
        {'name': 'My Custom Cafe', 'day': 1, 'time_of_day': 'afternoon', 'address': '123 Main St', 'location': (16.050000, 108.220000)}, # Custom with coords
        {'name': 'The Marble Mountains', 'day': 2, 'time_of_day': 'morning', 'address': None}, # Known, no explicit coords in spec
        {'name': 'Unknown Bookstore', 'day': 2, 'time_of_day': 'evening', 'address': 'Somewhere in Da Nang'} # Custom, no coords
    ]
    # The 'location' key in specific_stops_test is what the tool layer should ideally provide if it can geocode.
    # If 'location' is missing or None for a custom stop, find_or_create_place_details will use (0,0).
    
    # full_plan_with_specific = optimize_distance_tour('2 days', user_specified_stops_for_modification=specific_stops_test)
    # print("\n--- Generated Itinerary Data (WITH Specific Stops) ---")
    # print(json.dumps(full_plan_with_specific, indent=2, ensure_ascii=False))
    print("--- End Test ---")

if __name__ == "__main__":
    test_optimize_distance_tour()


    