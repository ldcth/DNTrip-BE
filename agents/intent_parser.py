import re
from typing import Dict, Any, List

def parse_intent(query: str) -> Dict[str, Any]:
    """
    Parses a user query to extract structured information for retrieval.

    Args:
        query: The user's natural language query.

    Returns:
        A dictionary containing the parsed intent.
    """
    query = query.lower()
    intent = {
        "entity_type": None,
        "top_k": 5,  # Default to 5
        "location_filter": None,
        "sort_by": "relevance",  # Default to relevance for semantic search
        "location_ref": None,
        "original_query": query
    }

    # 1. Parse top_k
    top_k_match = re.search(r"top (\d+)", query)
    if top_k_match:
        intent["top_k"] = int(top_k_match.group(1))
    else:
        # Fallback for queries like "best 2 hotels" or "show me 3 cafes"
        k_match = re.search(r"(\d+)", query)
        if k_match:
            k = int(k_match.group(1))
            # Set top_k only if it's a reasonable number
            if 1 <= k <= 50:
                intent["top_k"] = k

    # 2. Parse entity type (can be extended)
    # entity_keywords = ["restaurant", "restaurants", "cafe", "cafes", "destination", "destinations", "hotel", "hotels"]
    entity_keywords = [
    'tourist attraction', 'restaurant', 'cafe', 'bar',
    'bakery', 'supermarket',
    'shopping mall', 'store', 'souvenir store', 'clothing store', 'campground',
    'museum', 'art_gallery',
    'park', 'zoo', 'aquarium', 'amusement park', 'stadium',
    'hospital', 'pharmacy', 'atm'
]
    for entity in entity_keywords:
        if entity in query:
            # Normalize to singular
            intent["entity_type"] = entity.rstrip("s")
            break
    
    # If no specific type, default to "place"
    if not intent["entity_type"]:
        intent["entity_type"] = "place"

    # 3. Parse location filter and location_ref
    location_match = re.search(r"in (.+)", query)
    near_match = re.search(r"near (.+)", query)

    if near_match:
        intent["location_ref"] = near_match.group(1).strip()
        intent["sort_by"] = "distance"  # Suggest distance; retriever will validate
    elif location_match:
        location = location_match.group(1).strip()
        # A simple cleanup for common endings
        if "district" in location:
            location = location.replace("district", "").strip()
        intent["location_filter"] = location
        intent["sort_by"] = "rating" # Sort by rating for location-filtered queries

    # "top" or "best" implies sorting by rating, but distance has higher precedence
    if ("best" in query or "top" in query) and intent["sort_by"] != "distance":
        intent["sort_by"] = "rating"

    return intent 