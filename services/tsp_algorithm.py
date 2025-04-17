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
        return [{
            "place": selected_hotel.get("name", "Unknown Hotel"),
            "location": (lat, lon)
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
                restaurants_list.append({
                    "place": r.get("name", "Unknown Restaurant"),
                    "location": (lat, lon)
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
                # Process time_to_visit into a list/set for easier checking
                time_str = p.get("time_to_visit", "").lower()
                times = {t.strip() for t in time_str.split(',') if t.strip()}
                
                places_list.append({
                    "place": p.get("name", "Unknown Place"),
                    "location": (lat, lon),
                    "priority": priority,
                    "times": times
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
        return float('inf') # Return infinity for invalid coords

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
def select_places(places_list, time_of_day, count=1, already_selected_names=None):
    """Selects places based on time_of_day, biasing towards priority 1, ensuring uniqueness."""
    if already_selected_names is None:
        already_selected_names = set()

    # Filter by time_of_day and names not already selected
    eligible_places = [
        p for p in places_list 
        if time_of_day in p.get('times', set()) and p.get('place') not in already_selected_names
    ]
    
    if not eligible_places:
        return []

    # --- Weighted Selection Logic --- 
    priority_weight = 3 # Higher chance for priority 1
    other_weight = 1    # Lower chance for others

    weighted_eligible = []
    weights = []
    for p in eligible_places:
        weighted_eligible.append(p)
        weights.append(priority_weight if p.get('priority') == 1 else other_weight)

    num_available = len(weighted_eligible)
    num_to_select = min(count, num_available)
    
    selected = []
    if num_to_select == 0:
        return []
    elif num_to_select == 1:
        chosen = random.choices(weighted_eligible, weights=weights, k=1)[0]
        selected.append(chosen)
    elif num_to_select == 2:
        # Select first weighted
        chosen1 = random.choices(weighted_eligible, weights=weights, k=1)[0]
        selected.append(chosen1)
        
        # Prepare for second selection (remove first chosen)
        remaining_eligible = []
        remaining_weights = []
        for i, p in enumerate(weighted_eligible):
            if p['place'] != chosen1['place']: # Compare by name for uniqueness
                remaining_eligible.append(p)
                remaining_weights.append(weights[i])
        
        # Select second weighted if possible
        if remaining_eligible:
            chosen2 = random.choices(remaining_eligible, weights=remaining_weights, k=1)[0]
            selected.append(chosen2)

    return selected

def select_restaurants(restaurants_list, count=1, already_selected_names=None):
    """Selects random restaurants, ensuring uniqueness."""
    if already_selected_names is None:
        already_selected_names = set()

    # Filter out restaurants already selected
    eligible_restaurants = [
        r for r in restaurants_list 
        if r.get('place') not in already_selected_names
    ]

    if not eligible_restaurants or count <= 0:
        return []
        
    actual_count = min(count, len(eligible_restaurants))
    return random.sample(eligible_restaurants, actual_count)


def optimize_distance_tour(travel_duration):
    travel_duration = process_travel_duration(travel_duration)

    # --- 1. Load Data ---
    location_hotel_list = get_location_hotel()
    if not location_hotel_list:
        # Return an error structure or raise an exception
        return {"error": "Itinerary generation failed: No hotel data."}
    location_hotel = location_hotel_list[0]
    hotel_name = location_hotel["place"]
    hotel_coords = tuple(location_hotel["location"])
    # Keep this print for feedback during direct script execution
    print(f"Selected Hotel: {hotel_name} at {hotel_coords}") 

    must_visit_places = get_must_visit_places()
    restaurants = get_restaurants()

    # --- Initialize Sets for Uniqueness Tracking ---
    selected_places_ever = set()
    selected_restaurants_ever = set()

    # --- Initialize Result Structure --- 
    itinerary_result = {
        "hotel": {"name": hotel_name, "coords": hotel_coords},
        "daily_plans": []
    }

    # Create a combined map (optional, but can be useful)
    all_locations_map = {hotel_coords: hotel_name}
    if must_visit_places:
        all_locations_map.update({tuple(p["location"]): p["place"] for p in must_visit_places})
    if restaurants:
        all_locations_map.update({tuple(r["location"]): r["place"] for r in restaurants})

    if not must_visit_places:
        print("Warning: No must-visit places loaded.")
    if not restaurants:
        print("Warning: No restaurants loaded.")

    # --- 2. Loop Through Days ---    
    for day_index in range(travel_duration):
        day_data = {
            "day": day_index + 1,
            "planned_stops": {},
            "route": []
        }
        
        # --- 3. Select Locations for the Day (Ensuring Uniqueness) ---
        daily_plan_selection = {}
        
        morning_places = select_places(must_visit_places, 'morning', 1, selected_places_ever)
        daily_plan_selection['Morning'] = morning_places
        for place in morning_places: selected_places_ever.add(place['place'])

        lunch_restaurants = select_restaurants(restaurants, 1, selected_restaurants_ever)
        daily_plan_selection['Lunch'] = lunch_restaurants
        for r in lunch_restaurants: selected_restaurants_ever.add(r['place'])

        afternoon_places = select_places(must_visit_places, 'afternoon', 1, selected_places_ever)
        daily_plan_selection['Afternoon'] = afternoon_places
        for place in afternoon_places: selected_places_ever.add(place['place'])
        
        dinner_restaurants = select_restaurants(restaurants, 1, selected_restaurants_ever)
        daily_plan_selection['Dinner'] = dinner_restaurants
        for r in dinner_restaurants: selected_restaurants_ever.add(r['place'])
       
        evening_count = random.randint(1, 2)
        evening_places = select_places(must_visit_places, 'evening', evening_count, selected_places_ever)
        daily_plan_selection['Evening'] = evening_places
        for place in evening_places: selected_places_ever.add(place['place'])
        
        # --- 4. Populate Planned Stops in Result --- 
        for time_slot, items in daily_plan_selection.items():
            day_data["planned_stops"][time_slot] = [item['place'] for item in items]
            
        # --- 5. Generate Sequential Route and Populate in Result --- 
        current_coords = hotel_coords
        current_name = hotel_name
        step_counter = 0
        # Add starting point to the route
        day_data["route"].append({
            "step": step_counter,
            "time_slot": "Start",
            "type": "hotel",
            "name": current_name,
            "coords": current_coords,
            "distance_from_previous_km": 0.0
        })

        # Process time slots sequentially
        for time_slot in ['Morning', 'Lunch', 'Afternoon', 'Dinner', 'Evening']:
            items_for_slot = daily_plan_selection.get(time_slot, [])
                 
            for item in items_for_slot:
                step_counter += 1
                next_coords = tuple(item["location"])
                next_name = item["place"]
                distance_km = haversine(current_coords, next_coords)
                
                # Determine type (simple check based on time slot)
                location_type = "restaurant" if time_slot in ['Lunch', 'Dinner'] else "place"

                day_data["route"].append({
                    "step": step_counter,
                    "time_slot": time_slot,
                    "type": location_type,
                    "name": next_name,
                    "coords": next_coords,
                    "distance_from_previous_km": round(distance_km, 2)
                })
                
                # Update current location for the next step
                current_coords = next_coords
                current_name = next_name
        
        itinerary_result["daily_plans"].append(day_data)
            
    # Removed internal print statements for itinerary generation
    return itinerary_result # Return the structured data


# --- Test function ---
def test_optimize_distance_tour():
    print("Testing itinerary generation for '3 days 2 nights'...")
    # Store the returned dictionary
    full_plan = optimize_distance_tour('3 days 2 nights') 
    
    # Print the result using json.dumps for pretty printing
    print("\n--- Generated Itinerary Data ---")
    print(json.dumps(full_plan, indent=2, ensure_ascii=False)) # ensure_ascii=False for non-English characters
    print("--- End Test ---")

if __name__ == "__main__":
    test_optimize_distance_tour()


    