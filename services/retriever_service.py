import json
import os
from typing import List, Dict, Any
from math import radians, sin, cos, sqrt, atan2
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

class RetrieverService:
    def __init__(self, data_path="scrapper/data"):
        self.data_path = data_path
        
        self.places = self._load_data("combined_data.json")
        self.hotels = self._load_data("tripadvisor_da_nang_final_details.json")
        
        self._process_hotel_data()
        
        self.all_places = self.places + self.hotels
        
        self.place_names_by_category = {}
        for place in self.all_places:
            category = place.get("category", "unknown")
            if category not in self.place_names_by_category:
                self.place_names_by_category[category] = set()
            self.place_names_by_category[category].add(place.get("name"))
        
        # For backward compatibility
        self.restaurant_names = self.place_names_by_category.get("restaurant", set()) | self.place_names_by_category.get("cafe", set())
        self.hotel_names = self.place_names_by_category.get("hotel", set())
        
        # Load semantic search components
        self.index = None
        self.mapping = None
        self.model = None
        try:
            index_path = os.path.join(self.data_path, "semantic_index.faiss")
            mapping_path = os.path.join(self.data_path, "semantic_mapping.json")
            
            self.index = faiss.read_index(index_path)
            with open(mapping_path, 'r', encoding='utf-8') as f:
                # json keys are strings, so convert them back to integers
                self.mapping = {int(k): v for k, v in json.load(f).items()}
            
            self.model = SentenceTransformer('all-MiniLM-L6-v2')
            print("Successfully loaded semantic search index and model.")
        except Exception as e:
            print(f"Warning: Could not load semantic search components. Semantic search will be disabled. Error: {e}")

    def _load_data(self, filename: str) -> List[Dict[str, Any]]:
        """Loads a JSON data file and tags each item with its source filename."""
        file_path = os.path.join(self.data_path, filename)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for item in data:
                    item['source_file'] = filename  # Tag with source
                return data
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Warning: Could not load data from {file_path}. Error: {e}")
            return []

    def _process_hotel_data(self):
        """Process hotel data to match the combined data format."""
        for item in self.hotels:
            if 'rating_count' in item:
                item['list_rating'] = item['rating_count']
                del item['rating_count']
            
            item['category'] = 'hotel'
            
            if 'lat' in item and isinstance(item['lat'], str):
                try:
                    item['lat'] = float(item['lat'])
                except ValueError:
                    item['lat'] = None
            
            if 'lon' in item and isinstance(item['lon'], str):
                try:
                    item['lon'] = float(item['lon'])
                except ValueError:
                    item['lon'] = None
            
            if 'phone' not in item:
                item['phone'] = 'N/A'

    def get_places_by_category(self, category: str = None) -> List[Dict[str, Any]]:
        """Get places filtered by category."""
        if category is None:
            return self.all_places
        
        category = category.lower()
        return [p for p in self.all_places if p.get("category", "").lower() == category]

    @property
    def restaurants(self):
        """Get all restaurants and cafes from all places."""
        return [p for p in self.all_places if p.get("category") in ["restaurant", "cafe"]]

    def _calculate_haversine_distance(self, lat1, lon1, lat2, lon2):
        """Calculates the distance between two points on Earth."""
        R = 6371  # Radius of Earth in kilometers
        
        lat1_rad = radians(float(lat1))
        lon1_rad = radians(float(lon1))
        lat2_rad = radians(float(lat2))
        lon2_rad = radians(float(lon2))
        
        dlon = lon2_rad - lon1_rad
        dlat = lat2_rad - lat1_rad
        
        a = sin(dlat / 2)**2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon / 2)**2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        
        return R * c

    def _resolve_location_reference(self, location_ref: str) -> Dict[str, Any]:
        """Finds the coordinates of a named location using a case-insensitive search."""
        search_term = location_ref.lower()
        for place in self.all_places:
            if search_term in place.get("name", "").lower():
                return {
                    "lat": place.get("lat"),
                    "lon": place.get("lon")
                }
        return None

    def search_by_semantics(self, query: str, k: int, entity_type: str = None) -> List[Dict[str, Any]]:
        """Performs a semantic search using the FAISS index."""
        if not all([self.index, self.mapping, self.model]):
            print("Error: Semantic search is not available.")
            return []

        # Encode the query, ensuring the result is a CPU-based numpy array
        query_embedding = self.model.encode([query])
        query_embedding = np.array(query_embedding).astype('float32')

        # D: distances, I: indices
        distances, indices = self.index.search(query_embedding, k * 2)  # Fetch more to filter
        
        results = []
        found_names = set()
        for i in indices[0]:
            if i in self.mapping:
                mapped_item = self.mapping[i]
                # Find the full data from all_places
                full_item = next((p for p in self.all_places if p['name'] == mapped_item['name']), None)
                
                if full_item and full_item['name'] not in found_names:
                    # Filter by entity type if specified
                    if entity_type:
                        item_category = full_item.get('category', '').lower()
                        entity_type_lower = entity_type.lower()
                        
                        # Check if the item matches the requested entity type
                        if entity_type_lower == "hotel" and item_category != "hotel":
                            continue
                        elif entity_type_lower in ["restaurant", "cafe"] and item_category not in ["restaurant", "cafe"]:
                            continue
                        elif entity_type_lower not in ["hotel", "restaurant", "cafe"] and item_category != entity_type_lower:
                            continue
                    
                    results.append(full_item)
                    found_names.add(full_item['name'])

            if len(results) >= k:
                break
        
        return results

    def retrieve_places(self, intent: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Retrieves places based on a structured intent.
        """
        entity_type = intent.get("entity_type", "place")
        top_k = intent.get("top_k", 5)
        location_filter = intent.get("location_filter")
        location_ref = intent.get("location_ref")
        sort_by = intent.get("sort_by", "rating")
        original_query = intent.get("original_query")

        # --- DECISION LOGIC ---
        
        # 1. Prioritize distance search if a resolvable location reference is given
        if location_ref:
            print("--- Attempting Distance Search ---")
            ref_location = self._resolve_location_reference(location_ref)
            if ref_location and ref_location.get("lat") and ref_location.get("lon"):
                # Get appropriate source data based on entity type
                if entity_type and entity_type.lower() != "place":
                    source_data = self.get_places_by_category(entity_type)
                else:
                    source_data = self.all_places
                
                # Calculate distances
                for place in source_data:
                    place_lat = place.get("lat")
                    place_lon = place.get("lon")
                    if place_lat and place_lon:
                        distance = self._calculate_haversine_distance(
                            ref_location["lat"], ref_location["lon"],
                            place_lat, place_lon
                        )
                        place["distance_km"] = round(distance, 2)
                
                # Filter and sort by distance
                source_data = [p for p in source_data if "distance_km" in p]
                source_data.sort(key=lambda x: x["distance_km"])
                return source_data[:top_k]
            else:
                print(f"Warning: Could not resolve location reference '{location_ref}'. Falling back to semantic search.")
                # Explicitly fall back to semantic search if location ref fails
                return self.search_by_semantics(original_query, top_k, entity_type)
        
        # 2. If a location filter is provided, perform a keyword search on the address
        if location_filter:
            print("--- Performing Keyword Search on Location ---")
            # Get appropriate source data based on entity type
            if entity_type and entity_type.lower() != "place":
                source_data = self.get_places_by_category(entity_type)
            else:
                source_data = self.all_places
            
            filtered_results = [
                place for place in source_data
                if location_filter in place.get("address", "").lower()
            ]
            
            # Sort by rating
            filtered_results.sort(
                key=lambda x: float(str(x.get("rating", "0")).replace(",", ".")),
                reverse=True
            )
            return filtered_results[:top_k]

        # 3. Default to semantic search for all other queries
        print("--- Performing Semantic Search ---")
        return self.search_by_semantics(original_query, top_k, entity_type) 