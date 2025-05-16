import numpy as np
import re
import json
import random
import math # Import math for Haversine

# --- Helper functions to load data ---
def get_location_hotel():
    """Reads hotel data, selects one randomly, and returns its info."""
    try:
        with open("scrapper/data/hotels.json", "r", encoding='utf-8') as f:
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
        with open("scrapper/data/restaurants.json", "r", encoding='utf-8') as f:
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
        with open("scrapper/data/must.json", "r", encoding='utf-8') as f:
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
    If not found, creates a synthetic entry using stop_spec.
    stop_spec is a dict like {'name': ..., 'day': ..., 'time_of_day': ..., 'address': ..., 'location': (lat,lon) or None}
    The 'location' field in stop_spec is assumed to be (lat, lon) if present.
    Returns a place-like dictionary.
    """
    place_name = stop_spec['name']
    time_of_day = stop_spec['time_of_day'].lower()

    # Check in must-visit places
    for p in must_visit_places_list:
        if p['place'].lower() == place_name.lower():
            # Return a copy to avoid modifying the original list items if we add/change keys later
            place_detail = p.copy()
            # Ensure it has a 'type' for routing logic if needed, default to 'place'
            place_detail.setdefault('type', 'place') 
            return place_detail

    # Check in restaurants (if it's a lunch/dinner slot, or if user specifies a restaurant as a "place")
    # This part might need refinement based on how user specifies restaurants vs places.
    # For now, if it's not in must_visit, check restaurants too.
    for r in all_restaurants_list:
        if r['place'].lower() == place_name.lower():
            restaurant_detail = r.copy()
            restaurant_detail.setdefault('type', 'restaurant')
            # Restaurants from json don't have 'times', add one based on spec
            restaurant_detail['times'] = {time_of_day} 
            # Restaurants from json might not have 'priority'
            restaurant_detail.setdefault('priority', 1) # Assume user-specified is high priority
            return restaurant_detail

    # If not found, create a synthetic entry (custom location)
    # Default to (0,0) if no location, which will make Haversine return large distance or error if not handled.
    # The caller (optimize_distance_tour) should be aware of this.
    custom_location = stop_spec.get('location') # This should be (lat, lon) tuple if available from tool
    if custom_location:
        try:
            # Ensure it's float tuple
            custom_location = (float(custom_location[0]), float(custom_location[1]))
        except (TypeError, ValueError, IndexError):
            print(f"Warning: Invalid custom location format for '{place_name}': {custom_location}. Using (0,0).")
            custom_location = (0.0, 0.0) # Fallback
    else:
        # No coordinates provided for custom stop. This will make distance calculation difficult/impossible.
        print(f"Warning: No coordinates provided for custom stop '{place_name}'. Using (0,0) and relying on address in description.")
        custom_location = (0.0, 0.0) # Fallback

    description = f"User-specified visit: {place_name}"
    if stop_spec.get('address'):
        description += f" at {stop_spec['address']}"
    if custom_location == (0.0, 0.0) and not stop_spec.get('address'):
        description += " (Location details not provided)"
    elif custom_location == (0.0, 0.0) and stop_spec.get('address'):
         description += " (Coordinates not found, address provided)"


    return {
        "place": place_name,
        "location": custom_location,
        "priority": 0,  # Highest priority as it's user-specified
        "times": {time_of_day}, # Based on user's specification
        "description": description,
        "type": "place" # Default type, could be 'custom_place'
    }

def optimize_distance_tour(travel_duration_str, user_specified_stops_for_modification=None, previous_base_plan_data=None):
    travel_duration_days = process_travel_duration(travel_duration_str)
    if travel_duration_days is None or travel_duration_days <= 0:
        return {"error": "Invalid travel duration provided."}

    # --- 1. Load Data ---
    location_hotel_list = get_location_hotel()
    if not location_hotel_list:
        return {"error": "Itinerary generation failed: No hotel data."}
    
    # --- Hotel Handling: Use from previous plan if available and valid, otherwise pick new ---
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
    
    if not hotel_coords: # If not set from previous plan or if previous was invalid
        selected_hotel_info = location_hotel_list[0]
        hotel_name = selected_hotel_info["place"]
        hotel_coords = tuple(selected_hotel_info["location"]) # Ensure it's a tuple
        hotel_description = selected_hotel_info.get("description", f"Accommodation: {hotel_name}")
        print(f"Selected New Hotel: {hotel_name} at {hotel_coords}")

    must_visit_places = get_must_visit_places()
    restaurants = get_restaurants()

    # --- Process user_specified_stops_for_modification (these are the DELTAS/OVERRIDES) ---    
    # These stops will directly replace or be added, taking precedence.
    # Map: { (day_number, time_slot_str_lower): [list_of_stop_specs_as_dicts] }
    modification_stops_map = {}
    print(f"DEBUG TSP: User specified stops for modification (deltas): {user_specified_stops_for_modification}")
    if user_specified_stops_for_modification:
        for stop_item_idx, stop_item in enumerate(user_specified_stops_for_modification):
            try:
                day_key = int(stop_item['day'])
                time_key = stop_item['time_of_day'].lower()
                map_key = (day_key, time_key)
                if map_key not in modification_stops_map:
                    modification_stops_map[map_key] = []
                modification_stops_map[map_key].append(stop_item) # stop_item is already a dict
            except (KeyError, ValueError, TypeError) as e:
                print(f"Warning DEBUG TSP: Skipping invalid modification stop (item #{stop_item_idx}: {stop_item}) due to parsing error: {e}")
                continue
    print(f"DEBUG TSP: Modification stops map (deltas processed): {modification_stops_map}")

    # --- Initialize Sets for Uniqueness Tracking --- 
    # This set will track all places chosen (from previous plan, from modifications, or newly selected)
    # to ensure variety if new places need to be auto-selected.
    selected_places_ever = set()

    # --- Initialize Result Structure --- 
    itinerary_result = {
        "hotel": {"name": hotel_name, "coords": list(hotel_coords), "description": hotel_description},
        "daily_plans": []
    }

    # --- 2. Loop Through Days ---    
    for day_index in range(travel_duration_days):
        current_day_number = day_index + 1
        print(f"DEBUG TSP: --- Starting Day {current_day_number} of {travel_duration_days} ---")
        day_data = {
            "day": current_day_number,
            "planned_stops": {}, # Will store lists of place names for each slot
            "route": []
        }
        
        daily_plan_items_by_slot = {} 

        # --- 3. Select Locations for the Day (Incorporating Modifications and Previous Plan) ---
        time_slots_of_day = ['morning', 'lunch', 'afternoon', 'dinner', 'evening'] # Define order

        for time_slot_lower in time_slots_of_day:
            current_slot_key = (current_day_number, time_slot_lower)
            slot_places_for_day = []
            slot_already_filled_by_modification = False

            # Priority 1: Apply direct modifications for this slot
            if current_slot_key in modification_stops_map:
                user_modification_stop_specs = modification_stops_map[current_slot_key]
                print(f"DEBUG TSP: Day {current_day_number} {time_slot_lower.capitalize()} - Applying MODIFICATION: {user_modification_stop_specs}")
                for stop_spec_dict in user_modification_stop_specs:
                    place_detail = find_or_create_place_details(stop_spec_dict, must_visit_places, restaurants)
                    if time_slot_lower in ['lunch', 'dinner']:
                         place_detail['type'] = 'restaurant' # Ensure type if it's a meal slot
                    slot_places_for_day.append(place_detail)
                    if isinstance(place_detail.get('place'), str):
                        selected_places_ever.add(place_detail['place'].lower())
                slot_already_filled_by_modification = True # Mark as filled by explicit change
            
            # Priority 2: If not modified, try to preserve from previous base plan
            if not slot_already_filled_by_modification and previous_base_plan_data:
                # Find the corresponding day in previous_base_plan_data
                prev_day_plan_data = next((dp for dp in previous_base_plan_data.get('daily_plans', []) if dp.get('day') == current_day_number), None)
                if prev_day_plan_data and isinstance(prev_day_plan_data.get('planned_stops'), dict):
                    # Time slot keys in stored planned_stops might be capitalized (e.g., 'Morning')
                    # We need to find the right key, case-insensitively for robustness, or ensure consistency.
                    # For now, assume keys in planned_stops are like 'Morning', 'Lunch' etc.
                    # We need to map time_slot_lower (e.g. 'morning') to the key in prev_day_plan_data.planned_stops
                    # This is brittle. Better: ensure keys are consistent or use a mapping.
                    # Let's assume stored keys are Capitalized for now.
                    time_slot_capitalized = time_slot_lower.capitalize()
                    
                    # More robust check for time slot key in previous plan
                    prev_slot_name_found = None
                    for k in prev_day_plan_data['planned_stops'].keys():
                        if k.lower() == time_slot_lower:
                            prev_slot_name_found = k
                            break

                    if prev_slot_name_found and prev_day_plan_data['planned_stops'].get(prev_slot_name_found):
                        preserved_place_names = prev_day_plan_data['planned_stops'][prev_slot_name_found]
                        print(f"DEBUG TSP: Day {current_day_number} {time_slot_lower.capitalize()} - Preserving from PREVIOUS plan: {preserved_place_names}")
                        for place_name in preserved_place_names:
                            # We need to reconstruct full place_detail for preserved items.
                            # This requires looking them up in must_visit_places or restaurants, or creating a synthetic one.
                            # We can use find_or_create_place_details by mocking a stop_spec.
                            # For location, we need to find it in the previous plan's route if possible.
                            mock_stop_spec = {'name': place_name, 'day': current_day_number, 'time_of_day': time_slot_lower}
                            
                            # Try to find location from previous plan's route for more accuracy
                            prev_route_stop_info = None
                            if prev_day_plan_data.get('route'):
                                for r_stop in prev_day_plan_data['route']:
                                    if r_stop.get('name') == place_name and r_stop.get('time_slot', '').lower() == time_slot_lower:
                                        if isinstance(r_stop.get('coords'), list) and len(r_stop['coords']) == 2:
                                            mock_stop_spec['location'] = tuple(r_stop['coords'])
                                            # mock_stop_spec['address'] = r_stop.get('address') # if address was stored in route
                                        break
                            
                            place_detail = find_or_create_place_details(mock_stop_spec, must_visit_places, restaurants)
                            if time_slot_lower in ['lunch', 'dinner']:
                                place_detail['type'] = 'restaurant' # Ensure type
                            slot_places_for_day.append(place_detail)
                            if isinstance(place_detail.get('place'), str):
                                selected_places_ever.add(place_detail['place'].lower())
            
            # Priority 3: If slot is still empty (not modified, nothing to preserve or preserve failed), then auto-select.
            if not slot_places_for_day: # If list is still empty
                print(f"DEBUG TSP: Day {current_day_number} {time_slot_lower.capitalize()} - Slot empty, AUTO-SELECTING.")
                if time_slot_lower == 'lunch':
                    selected_items = select_restaurants(restaurants, 1, selected_places_ever)
                elif time_slot_lower == 'dinner':
                    selected_items = select_restaurants(restaurants, 1, selected_places_ever)
                elif time_slot_lower == 'evening':
                    evening_count = random.randint(1, 2)
                    selected_items = select_places(must_visit_places, time_slot_lower, evening_count, selected_places_ever)
                else: # Morning, Afternoon
                    selected_items = select_places(must_visit_places, time_slot_lower, 1, selected_places_ever)
                
                slot_places_for_day.extend(selected_items)
                for p_item in selected_items:
                    if isinstance(p_item.get('place'), str):
                        selected_places_ever.add(p_item['place'].lower())
            
            daily_plan_items_by_slot[time_slot_lower.capitalize()] = slot_places_for_day # Store with Capitalized key for consistency

        # --- 4. Populate Planned Stops (names) in Result --- 
        for time_slot_capitalized_key, items_list in daily_plan_items_by_slot.items():
            day_data["planned_stops"][time_slot_capitalized_key] = [item['place'] for item in items_list]
            
        # --- 5. Generate Sequential Route and Populate in Result --- 
        current_route_coords = hotel_coords # Start route from hotel for the day
        # current_route_name = hotel_name
        step_counter = 0
        day_data["route"].append({
            "step": step_counter,
            "time_slot": "Start",
            "type": "hotel",
            "name": hotel_name,
            "coords": list(hotel_coords),
            "distance_from_previous_km": 0.0,
            "description": hotel_description
        })

        # Ensure consistent iteration order for route generation
        # The daily_plan_items_by_slot keys are already Capitalized e.g. 'Morning'
        ordered_time_slots_for_route = ['Morning', 'Lunch', 'Afternoon', 'Dinner', 'Evening']

        for time_slot_key_for_route in ordered_time_slots_for_route:
            items_for_slot = daily_plan_items_by_slot.get(time_slot_key_for_route, [])
                 
            for item_dict in items_for_slot:
                step_counter += 1
                try:
                    next_coords_raw = item_dict["location"]
                    next_coords = (float(next_coords_raw[0]), float(next_coords_raw[1]))
                except (TypeError, ValueError, IndexError):
                    print(f"Warning: Invalid coordinates for {item_dict['place']} in routing: {item_dict.get('location')}. Using fallback (0,0).")
                    next_coords = (0.0, 0.0)

                next_name = item_dict["place"]
                distance_km = haversine(current_route_coords, next_coords)
                
                route_stop_data = {
                    "step": step_counter,
                    "time_slot": time_slot_key_for_route, # Use the capitalized key for time_slot
                    "name": next_name,
                    "coords": list(next_coords),
                    "distance_from_previous_km": round(distance_km, 2),
                    "description": item_dict.get("description", f"Visit to {next_name}")
                }
                route_stop_data["type"] = item_dict.get("type", "place") 
                if time_slot_key_for_route in ['Lunch', 'Dinner'] and route_stop_data["type"] != 'restaurant':
                     route_stop_data["type"] = "restaurant"

                day_data["route"].append(route_stop_data)
                current_route_coords = next_coords
                # current_route_name = next_name # Not strictly needed here
        
        itinerary_result["daily_plans"].append(day_data)
            
    return itinerary_result


# --- Test function ---
def test_optimize_distance_tour():
    print("Testing itinerary generation for '3 days 2 nights'...")
    full_plan_no_specific = optimize_distance_tour('3 days 2 nights') 
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
    
    full_plan_with_specific = optimize_distance_tour('2 days', user_specified_stops_for_modification=specific_stops_test)
    print("\n--- Generated Itinerary Data (WITH Specific Stops) ---")
    print(json.dumps(full_plan_with_specific, indent=2, ensure_ascii=False))
    print("--- End Test ---")

if __name__ == "__main__":
    test_optimize_distance_tour()


    