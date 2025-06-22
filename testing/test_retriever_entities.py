"""
Test script for RetrieverService to test different entity types
"""

import json
import sys
import os
from typing import Dict, Any, List

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.retriever_service import RetrieverService

def print_results(title: str, results: List[Dict[str, Any]], max_results: int = 3):
    """Print search results in a formatted way"""
    print(f"\n{'='*60}")
    print(f"🔍 {title}")
    print(f"{'='*60}")
    
    if not results:
        print("❌ No results found")
        return
    
    print(f"✅ Found {len(results)} results (showing top {min(len(results), max_results)}):")
    
    for i, place in enumerate(results[:max_results], 1):
        print(f"\n{i}. 📍 {place.get('name', 'N/A')}")
        print(f"   Category: {place.get('category', 'N/A')}")
        print(f"   Rating: {place.get('rating', 'N/A')} ({place.get('list_rating', 'N/A')} reviews)")
        print(f"   Address: {place.get('address', 'N/A')}")
        if 'distance_km' in place:
            print(f"   Distance: {place['distance_km']} km")
        print(f"   Source: {place.get('source_file', 'N/A')}")

def test_entity_types():
    """Test different entity types"""
    print("🚀 Starting RetrieverService Entity Type Tests")
    print("=" * 60)
    
    try:
        retriever = RetrieverService()
        print("✅ RetrieverService initialized successfully")
    except Exception as e:
        print(f"❌ Failed to initialize RetrieverService: {e}")
        return
    
    test_cases = [
        {
            "title": "Tourist Attractions - Semantic Search",
            "intent": {
                "entity_type": "tourist_attraction",
                "top_k": 5,
                "original_query": "famous tourist attractions"
            }
        },
        
        # Restaurants
        {
            "title": "Restaurants - High Rating",
            "intent": {
                "entity_type": "restaurant",
                "top_k": 5,
                "sort_by": "rating",
                "original_query": "best restaurants"
            }
        },
        
        # Cafes
        {
            "title": "Cafes - Semantic Search",
            "intent": {
                "entity_type": "cafe",
                "top_k": 5,
                "original_query": "coffee shops"
            }
        },
        
        # Hotels
        {
            "title": "Hotels - Near Beach",
            "intent": {
                "entity_type": "hotel",
                "top_k": 5,
                "location_ref": "My Khe Beach",
                "original_query": "hotels near beach"
            }
        },
        
        # Museums
        {
            "title": "Museums - Cultural Sites",
            "intent": {
                "entity_type": "museum",
                "top_k": 5,
                "original_query": "museums"
            }
        },
        
        # Art Galleries
        {
            "title": "Art Galleries",
            "intent": {
                "entity_type": "art_gallery",
                "top_k": 5,
                "original_query": "art galleries"
            }
        },
        
        # Shopping Malls
        {
            "title": "Shopping Malls",
            "intent": {
                "entity_type": "shopping_mall",
                "top_k": 5,
                "original_query": "shopping centers"
            }
        },
        
        # Souvenir Stores
        {
            "title": "Souvenir Stores - Near Dragon Bridge",
            "intent": {
                "entity_type": "souvenir_store",
                "top_k": 5,
                "location_ref": "Dragon Bridge",
                "original_query": "souvenir shops near dragon bridge"
            }
        },
        
        # Parks
        {
            "title": "Parks and Green Spaces",
            "intent": {
                "entity_type": "park",
                "top_k": 5,
                "original_query": "parks"
            }
        },
        
        # Bars
        {
            "title": "Bars and Nightlife",
            "intent": {
                "entity_type": "bar",
                "top_k": 5,
                "original_query": "bars nightlife"
            }
        },
        
        # Bakeries
        {
            "title": "Bakeries",
            "intent": {
                "entity_type": "bakery",
                "top_k": 5,
                "original_query": "bakeries"
            }
        },
        
        # Supermarkets
        {
            "title": "Supermarkets",
            "intent": {
                "entity_type": "supermarket",
                "top_k": 5,
                "original_query": "supermarkets"
            }
        },
        
        # Clothing Stores
        {
            "title": "Clothing Stores",
            "intent": {
                "entity_type": "clothing_store",
                "top_k": 5,
                "original_query": "clothing stores"
            }
        },
        
        # Campgrounds
        {
            "title": "Campgrounds and Glamping",
            "intent": {
                "entity_type": "campground",
                "top_k": 5,
                "original_query": "camping"
            }
        },
        
        # Location-based search
        {
            "title": "Restaurants in Hai Chau District",
            "intent": {
                "entity_type": "restaurant",
                "top_k": 5,
                "location_filter": "hai chau",
                "original_query": "restaurants in hai chau"
            }
        },
        
        # Distance-based search
        {
            "title": "Places near Vincom Plaza",
            "intent": {
                "entity_type": "place",
                "top_k": 5,
                "location_ref": "Vincom Plaza",
                "original_query": "places near vincom plaza"
            }
        }
    ]
    
    # Run all test cases
    for test_case in test_cases:
        try:
            results = retriever.retrieve_places(test_case["intent"])
            print_results(test_case["title"], results)
        except Exception as e:
            print(f"\n❌ Error in test '{test_case['title']}': {e}")
    
    # Test category statistics
    print_category_statistics(retriever)

def print_category_statistics(retriever: RetrieverService):
    """Print statistics about available categories"""
    print(f"\n{'='*60}")
    print("📊 CATEGORY STATISTICS")
    print(f"{'='*60}")
    
    print(f"Total places loaded: {len(retriever.all_places)}")
    print(f"Places from combined_data.json: {len(retriever.places)}")
    print(f"Hotels from tripadvisor: {len(retriever.hotels)}")
    
    print("\n📋 Available categories:")
    for category, names in retriever.place_names_by_category.items():
        print(f"  • {category}: {len(names)} places")
    
    # Test get_places_by_category method
    print(f"\n🔍 Testing get_places_by_category method:")
    test_categories = ['restaurant', 'hotel', 'cafe', 'museum', 'tourist_attraction']
    
    for category in test_categories:
        places = retriever.get_places_by_category(category)
        print(f"  • {category}: {len(places)} places")
        if places:
            print(f"    Example: {places[0].get('name', 'N/A')}")

def test_semantic_search():
    """Test semantic search specifically"""
    print(f"\n{'='*60}")
    print("🧠 SEMANTIC SEARCH TESTS")
    print(f"{'='*60}")
    
    retriever = RetrieverService()
    
    semantic_queries = [
        ("romantic dinner", "restaurant"),
        ("family fun activities", "tourist_attraction"),
        ("luxury accommodation", "hotel"),
        ("cultural experience", "museum"),
        ("shopping for clothes", "clothing_store"),
        ("morning coffee", "cafe"),
        ("souvenir shopping", "souvenir_store"),
        ("outdoor activities", "park")
    ]
    
    for query, entity_type in semantic_queries:
        try:
            results = retriever.search_by_semantics(query, k=3, entity_type=entity_type)
            print_results(f"Semantic: '{query}' -> {entity_type}", results, max_results=2)
        except Exception as e:
            print(f"❌ Error in semantic search '{query}': {e}")

def main():
    """Main test function"""
    print("🎯 RetrieverService Entity Type Test Suite")
    print("🕒 Starting comprehensive tests...")
    
    # Test different entity types
    test_entity_types()
    
    # Test semantic search
    test_semantic_search()
    
    print(f"\n{'='*60}")
    print("✅ All tests completed!")
    print(f"{'='*60}")

if __name__ == "__main__":
    main() 