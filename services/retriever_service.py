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
        self.restaurants = self._load_data("restaurants.json")
        self.hotels = self._load_data("tripadvisor_da_nang_final_details.json")
        self.all_places = self.restaurants + self.hotels
        
        # Create sets of names for efficient type checking
        self.restaurant_names = {p.get("name") for p in self.restaurants}
        self.hotel_names = {p.get("name") for p in self.hotels}
        
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
                    item['source_file'] = filename # Tag with source
                return data
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Warning: Could not load data from {file_path}. Error: {e}")
            return []

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
        distances, indices = self.index.search(query_embedding, k * 2) # Fetch more to filter
        
        results = []
        found_names = set()
        for i in indices[0]:
            if i in self.mapping:
                mapped_item = self.mapping[i]
                # Find the full data from all_places
                full_item = next((p for p in self.all_places if p['name'] == mapped_item['name']), None)
                
                if full_item and full_item['name'] not in found_names:
                    item_name = full_item.get('name')
                    # Robust type checking
                    is_hotel = item_name in self.hotel_names
                    is_restaurant = item_name in self.restaurant_names

                    if entity_type == "hotel" and not is_hotel:
                        continue
                    if (entity_type == "restaurant" or entity_type == "cafe") and not is_restaurant:
                        continue
                    
                    results.append(full_item)
                    found_names.add(item_name)

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
                source_data = self.all_places
                if entity_type == "restaurant" or entity_type == "cafe":
                    source_data = self.restaurants
                elif entity_type == "hotel":
                    source_data = self.hotels
                
                for place in source_data:
                    place_lat = place.get("lat")
                    place_lon = place.get("lon")
                    if place_lat and place_lon:
                        distance = self._calculate_haversine_distance(
                            ref_location["lat"], ref_location["lon"],
                            place_lat, place_lon
                        )
                        place["distance_km"] = round(distance, 2)
                
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
            source_data = []
            if entity_type == "restaurant" or entity_type == "cafe":
                source_data = self.restaurants
            elif entity_type == "hotel":
                source_data = self.hotels
            else:
                source_data = self.all_places
            
            filtered_results = [
                place for place in source_data
                if location_filter in place.get("address", "").lower()
            ]
            
            filtered_results.sort(
                key=lambda x: float(x.get("rating", "0").replace(",", ".")),
                reverse=True
            )
            return filtered_results[:top_k]

        # 3. Default to semantic search for all other queries
        print("--- Performing Semantic Search ---")
        return self.search_by_semantics(original_query, top_k, entity_type) 