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

def optimize_distance_tour(travel_duration_str, user_specified_stops=None): # Renamed arg for clarity
    travel_duration_days = process_travel_duration(travel_duration_str)
    if travel_duration_days is None or travel_duration_days <= 0:
        return {"error": "Invalid travel duration provided."}

    # --- 1. Load Data ---
    location_hotel_list = get_location_hotel()
    if not location_hotel_list:
        return {"error": "Itinerary generation failed: No hotel data."}
    location_hotel = location_hotel_list[0]
    hotel_name = location_hotel["place"]
    hotel_coords = tuple(location_hotel["location"])
    print(f"Selected Hotel: {hotel_name} at {hotel_coords}") 

    must_visit_places = get_must_visit_places()
    restaurants = get_restaurants()

    # --- Process user_specified_stops into a quick lookup map ---
    # Map: { (day_number, time_slot_str_lower): [list_of_stop_specs_as_dicts] }
    fixed_stops_map = {}
    print(f"DEBUG TSP: Initial user_specified_stops received by optimize_distance_tour: {user_specified_stops}") # DEBUG
    if user_specified_stops: # user_specified_stops is list of dicts or objects from the tool
        for stop_item_idx, stop_item in enumerate(user_specified_stops): # Renamed from stop_spec_dict for clarity
            print(f"DEBUG TSP: Processing stop_item #{stop_item_idx}: {stop_item}") # DEBUG
            try:
                stop_data_to_store = {}
                day_val_raw = None # For debugging
                if isinstance(stop_item, dict):
                    day_val_raw = stop_item['day']
                    print(f"DEBUG TSP: stop_item is dict. Raw day value: '{day_val_raw}' (type: {type(day_val_raw)})") # DEBUG
                    day_key = int(day_val_raw)
                    time_key = stop_item['time_of_day'].lower()
                    stop_data_to_store = stop_item # Already a dict
                else: # Assume it's a Pydantic-like object
                    day_val_raw = stop_item.day
                    print(f"DEBUG TSP: stop_item is object. Raw day value: '{day_val_raw}' (type: {type(day_val_raw)})") # DEBUG
                    day_key = int(day_val_raw)
                    time_key = stop_item.time_of_day.lower()
                    # Convert object to dict for consistent storage and usage
                    stop_data_to_store = {
                        'name': stop_item.name,
                        'day': stop_item.day,
                        'time_of_day': stop_item.time_of_day,
                        'address': getattr(stop_item, 'address', None)
                    }
                    # Handle location if the object has lat/lon attributes or a get_location_coordinates method
                    if hasattr(stop_item, 'get_location_coordinates'):
                        coords = stop_item.get_location_coordinates()
                        if coords:
                            stop_data_to_store['location'] = coords
                    elif hasattr(stop_item, 'latitude') and hasattr(stop_item, 'longitude') and \
                         stop_item.latitude is not None and stop_item.longitude is not None:
                        stop_data_to_store['location'] = (stop_item.latitude, stop_item.longitude)
                
                map_key = (day_key, time_key)
                print(f"DEBUG TSP: stop_item #{stop_item_idx} - Derived day_key: {day_key}, time_key: {time_key}. map_key for fixed_stops_map: {map_key}") # DEBUG
                if map_key not in fixed_stops_map:
                    fixed_stops_map[map_key] = []
                fixed_stops_map[map_key].append(stop_data_to_store) # Store the dictionary
            except (KeyError, ValueError, AttributeError, TypeError) as e: # Catch more potential errors
                print(f"Warning DEBUG TSP: Skipping invalid user_specified_stop (item #{stop_item_idx}: {stop_item}) due to parsing error: {e}") # DEBUG
                continue
    print(f"DEBUG TSP: Final fixed_stops_map after processing all user stops: {fixed_stops_map}") # DEBUG

    # --- Initialize Sets for Uniqueness Tracking ---
    selected_places_ever = set() # Tracks LOWERCASE names of places/restaurants to ensure variety
    # selected_restaurants_ever = set() # This can be merged into selected_places_ever if restaurants are also places

    # Add user-specified places to selected_places_ever to prevent re-selection by select_places
    if user_specified_stops:
        for stop_spec_dict in user_specified_stops: # This loop might be redundant if fixed_stops_map is primary source
                                                    # Or it should iterate over the processed dicts in fixed_stops_map values.
                                                    # For now, ensure it safely accesses 'name'.
            place_name = None
            if isinstance(stop_spec_dict, dict):
                place_name = stop_spec_dict.get('name')
            elif hasattr(stop_spec_dict, 'name'):
                place_name = stop_spec_dict.name
            
            if isinstance(place_name, str):
                selected_places_ever.add(place_name.lower())


    # --- Initialize Result Structure --- 
    itinerary_result = {
        "hotel": {"name": hotel_name, "coords": hotel_coords, "description": location_hotel["description"]},
        "daily_plans": []
    }
    print(f"DEBUG TSP: Entering daily planning loop. fixed_stops_map to be used: {fixed_stops_map}") # DEBUG

    # --- 2. Loop Through Days ---    
    for day_index in range(travel_duration_days):
        current_day_number = day_index + 1
        print(f"DEBUG TSP: --- Starting Day {current_day_number} of {travel_duration_days} ---") # DEBUG
        day_data = {
            "day": current_day_number,
            "planned_stops": {}, # Will store lists of place names for each slot
            "route": []
        }
        
        # This will store the actual place/restaurant objects for the day's plan
        daily_plan_items_by_slot = {} 
        
        # --- 3. Select Locations for the Day (Incorporating User Stops) ---
        
        # MORNING
        morning_stops_key = (current_day_number, 'morning')
        user_morning_stop_specs = fixed_stops_map.get(morning_stops_key, [])
        print(f"DEBUG TSP: Day {current_day_number} Morning - Lookup key for fixed_stops_map: {morning_stops_key}. Found user_morning_stop_specs: {user_morning_stop_specs}") # DEBUG
        morning_places_for_day = []
        if user_morning_stop_specs:
            for stop_spec_dict in user_morning_stop_specs: # stop_spec_dict is now guaranteed to be a dict
                place_detail = find_or_create_place_details(stop_spec_dict, must_visit_places, restaurants)
                morning_places_for_day.append(place_detail)
                if isinstance(place_detail.get('place'), str): # Add to tracker
                    selected_places_ever.add(place_detail['place'].lower()) 
        else:
            # If user didn't specify for this slot, pick one automatically
            morning_places_for_day = select_places(must_visit_places, 'morning', 1, selected_places_ever)
            for p in morning_places_for_day: 
                if isinstance(p.get('place'), str):
                    selected_places_ever.add(p['place'].lower())
        daily_plan_items_by_slot['Morning'] = morning_places_for_day

        # LUNCH
        # Assuming user doesn't specify lunch restaurants via 'user_specified_stops' in this iteration.
        # If they could, similar logic to MORNING would apply.
        # For now, restaurants are chosen by select_restaurants.
        # We need to ensure user-specified places (if they happen to be restaurants) are not re-selected.
        lunch_stops_key = (current_day_number, 'lunch')
        user_lunch_stop_specs = fixed_stops_map.get(lunch_stops_key, []) # Will be list of dicts
        print(f"DEBUG TSP: Day {current_day_number} Lunch - Lookup key for fixed_stops_map: {lunch_stops_key}. Found user_lunch_stop_specs: {user_lunch_stop_specs}") # DEBUG
        lunch_restaurants_for_day = []
        if user_lunch_stop_specs:
            for stop_spec_dict in user_lunch_stop_specs: # stop_spec_dict is a dict
                place_detail = find_or_create_place_details(stop_spec_dict, must_visit_places, restaurants)
                place_detail['type'] = 'restaurant'
                lunch_restaurants_for_day.append(place_detail)
                if isinstance(place_detail.get('place'), str):
                    selected_places_ever.add(place_detail['place'].lower()) 
        else:
            lunch_restaurants_for_day = select_restaurants(restaurants, 1, selected_places_ever) # Pass selected_places_ever
            for r in lunch_restaurants_for_day: 
                if isinstance(r.get('place'), str):
                    selected_places_ever.add(r['place'].lower())
        daily_plan_items_by_slot['Lunch'] = lunch_restaurants_for_day


        # AFTERNOON
        afternoon_stops_key = (current_day_number, 'afternoon')
        user_afternoon_stop_specs = fixed_stops_map.get(afternoon_stops_key, []) # Will be list of dicts
        print(f"DEBUG TSP: Day {current_day_number} Afternoon - Lookup key for fixed_stops_map: {afternoon_stops_key}. Found user_afternoon_stop_specs: {user_afternoon_stop_specs}") # DEBUG
        afternoon_places_for_day = []
        if user_afternoon_stop_specs:
            for stop_spec_dict in user_afternoon_stop_specs: # stop_spec_dict is a dict
                place_detail = find_or_create_place_details(stop_spec_dict, must_visit_places, restaurants)
                afternoon_places_for_day.append(place_detail)
                if isinstance(place_detail.get('place'), str):
                    selected_places_ever.add(place_detail['place'].lower())
        else:
            afternoon_places_for_day = select_places(must_visit_places, 'afternoon', 1, selected_places_ever)
            for p in afternoon_places_for_day: 
                if isinstance(p.get('place'), str):
                    selected_places_ever.add(p['place'].lower())
        daily_plan_items_by_slot['Afternoon'] = afternoon_places_for_day
        
        # DINNER
        dinner_stops_key = (current_day_number, 'dinner')
        user_dinner_stop_specs = fixed_stops_map.get(dinner_stops_key, []) # Will be list of dicts
        print(f"DEBUG TSP: Day {current_day_number} Dinner - Lookup key for fixed_stops_map: {dinner_stops_key}. Found user_dinner_stop_specs: {user_dinner_stop_specs}") # DEBUG
        dinner_restaurants_for_day = []
        if user_dinner_stop_specs:
            for stop_spec_dict in user_dinner_stop_specs: # stop_spec_dict is a dict
                place_detail = find_or_create_place_details(stop_spec_dict, must_visit_places, restaurants)
                place_detail['type'] = 'restaurant'
                dinner_restaurants_for_day.append(place_detail)
                if isinstance(place_detail.get('place'), str):
                    selected_places_ever.add(place_detail['place'].lower())
        else:
            dinner_restaurants_for_day = select_restaurants(restaurants, 1, selected_places_ever)
            for r in dinner_restaurants_for_day: 
                if isinstance(r.get('place'), str):
                    selected_places_ever.add(r['place'].lower())
        daily_plan_items_by_slot['Dinner'] = dinner_restaurants_for_day
       
        # EVENING
        evening_stops_key = (current_day_number, 'evening')
        user_evening_stop_specs = fixed_stops_map.get(evening_stops_key, []) # Will be list of dicts
        print(f"DEBUG TSP: Day {current_day_number} Evening - Lookup key for fixed_stops_map: {evening_stops_key}. Found user_evening_stop_specs: {user_evening_stop_specs}") # DEBUG
        evening_places_for_day = []
        if user_evening_stop_specs:
            for stop_spec_dict in user_evening_stop_specs: # stop_spec_dict is a dict
                place_detail = find_or_create_place_details(stop_spec_dict, must_visit_places, restaurants)
                evening_places_for_day.append(place_detail)
                if isinstance(place_detail.get('place'), str):
                    selected_places_ever.add(place_detail['place'].lower())
        else:
            evening_count = random.randint(1, 2) # Original logic for multiple evening places
            evening_places_for_day = select_places(must_visit_places, 'evening', evening_count, selected_places_ever)
            for p in evening_places_for_day: 
                if isinstance(p.get('place'), str):
                    selected_places_ever.add(p['place'].lower())
        daily_plan_items_by_slot['Evening'] = evening_places_for_day
        
        # --- 4. Populate Planned Stops (names) in Result --- 
        for time_slot, items_list in daily_plan_items_by_slot.items():
            day_data["planned_stops"][time_slot] = [item['place'] for item in items_list] # Store names
            
        # --- 5. Generate Sequential Route and Populate in Result --- 
        current_coords = hotel_coords
        current_name = hotel_name
        step_counter = 0
        day_data["route"].append({
            "step": step_counter,
            "time_slot": "Start",
            "type": "hotel",
            "name": current_name,
            "coords": current_coords,
            "distance_from_previous_km": 0.0,
            "description": location_hotel["description"]
        })

        for time_slot in ['Morning', 'Lunch', 'Afternoon', 'Dinner', 'Evening']:
            items_for_slot = daily_plan_items_by_slot.get(time_slot, []) # Get list of item dicts
                 
            for item_dict in items_for_slot: # item_dict is the full place/restaurant detail
                step_counter += 1
                # Ensure location is a tuple of floats for Haversine
                try:
                    next_coords_raw = item_dict["location"]
                    next_coords = (float(next_coords_raw[0]), float(next_coords_raw[1]))
                except (TypeError, ValueError, IndexError):
                    print(f"Warning: Invalid coordinates for {item_dict['place']} in routing: {item_dict.get('location')}. Using (0,0).")
                    next_coords = (0.0, 0.0) # Fallback for routing if coords are bad

                next_name = item_dict["place"]
                distance_km = haversine(current_coords, next_coords)
                
                route_stop_data = {
                    "step": step_counter,
                    "time_slot": time_slot,
                    "name": next_name,
                    "coords": list(next_coords), # Store as list in JSON
                    "distance_from_previous_km": round(distance_km, 2),
                    "description": item_dict.get("description", f"Visit to {next_name}") # Use the description from item_dict
                }
                # Determine type based on item_dict, or default
                route_stop_data["type"] = item_dict.get("type", "place") 
                # if time_slot in ['Lunch', 'Dinner'] and route_stop_data["type"] != 'restaurant':
                #     route_stop_data["type"] = "restaurant" # Override if it's a meal slot but type isn't set

                day_data["route"].append(route_stop_data)
                current_coords = next_coords
                current_name = next_name
        
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
    
    full_plan_with_specific = optimize_distance_tour('2 days', user_specified_stops=specific_stops_test)
    print("\n--- Generated Itinerary Data (WITH Specific Stops) ---")
    print(json.dumps(full_plan_with_specific, indent=2, ensure_ascii=False))
    print("--- End Test ---")

if __name__ == "__main__":
    test_optimize_distance_tour()


    