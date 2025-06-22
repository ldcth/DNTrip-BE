# tools.py
from langchain_core.tools import tool, StructuredTool
from pydantic import BaseModel, Field
from services.tsp_algorithm import optimize_distance_tour
from services.flight_picking import get_flights as get_flights_service # Renamed import
from services.retriever_service import RetrieverService  
from langchain_openai import ChatOpenAI  
from langchain_core.messages import SystemMessage, HumanMessage 
import json
import traceback
import os
from typing import List, Optional, Dict, Any 

class SpecificStop(BaseModel):
    name: str = Field(description="Name of the place or activity.")
    day: int = Field(description="The day number in the itinerary to visit this place (e.g., 1 for Day 1, 2 for Day 2).")
    time_of_day: str = Field(description="Preferred time to visit, e.g., 'morning', 'afternoon', 'evening'.")
    address: Optional[str] = Field(default=None, description="Optional. Address for custom locations if not a well-known attraction in Da Nang. This helps in identifying the place if it's not in the pre-defined list.")

class TravelPlanArgs(BaseModel):
    travel_duration: str = Field(description="The duration of the trip, e.g., '3 days 2 nights', '1 week', '5 ngay 4 dem'.")
    user_intention: str = Field(default="create", description="User's intent: 'create' for a new plan, 'modify' to adjust an existing plan. If 'modify', the agent system uses this to load the existing plan from memory. Defaults to 'create'.")
    user_specified_stops: Optional[List[SpecificStop]] = Field(default=None, description="Optional list of specific stops. If user_intention is 'modify', this list should ONLY contain the specific changes (additions/replacements) the user is requesting for the existing plan. If 'create', these are initial stops for a new plan. Each stop: name, day, time_of_day, optional address.")
    existing_plan_json: Optional[str] = Field(default=None, description="Optional JSON string of a complete plan. If user_intention is 'modify', the agent system populates this from memory; the LLM should NOT provide it. If user_intention is 'create' and this is provided, it acts as a base for a new plan (e.g., if user provides an old plan text).")

@tool("plan_da_nang_trip", args_schema=TravelPlanArgs)
def plan_da_nang_trip_tool(travel_duration: str, user_intention: str = "create", user_specified_stops: Optional[List[SpecificStop]] = None, existing_plan_json: Optional[str] = None) -> str:
    """
    Plans or modifies a travel itinerary for Da Nang.
    Behavior depends on 'user_intention' and the presence of 'existing_plan_json'.

    If 'user_intention' is 'modify' (system will ensure 'existing_plan_json' is populated from memory):
    - It modifies the existing plan. 'user_specified_stops' are treated as deltas (additions/replacements).

    If 'user_intention' is 'create':
    - If 'existing_plan_json' IS provided (e.g. user pasted an old plan): It uses that as a base for a new plan, incorporating 'user_specified_stops'.
    - If 'existing_plan_json' is NOT provided: A brand new plan is generated based on 'travel_duration' and any 'user_specified_stops'.

    The response is a JSON string with 'base_plan', 'user_specified_stops' (from current call), and 'notes'.
    """
    print(f"--- Calling Planner Tool ---")
    print(f"  Travel Duration: {travel_duration}")
    print(f"  User Intention: {user_intention}") # Log the intention
    if user_specified_stops:
        print(f"  User Specified Stops ({len(user_specified_stops)}):")
        for stop_idx, stop_obj in enumerate(user_specified_stops):
            print(f"    Stop {stop_idx + 1}: Name='{stop_obj.name}', Day={stop_obj.day}, Time='{stop_obj.time_of_day}', Address='{stop_obj.address}'")
    else:
        print("  User Specified Stops: None")

    if existing_plan_json:
        print(f"  Existing Plan JSON provided (length: {len(existing_plan_json)}):")
        # Log a snippet of the JSON to avoid excessively long logs.
        snippet_length = 300
        json_snippet = existing_plan_json[:snippet_length]
        if len(existing_plan_json) > snippet_length:
            json_snippet += "..."
        print(f"    Snippet: {json_snippet}")
        print(f"    Full existing_plan_json: {existing_plan_json}")
    else:
        print("  Existing Plan JSON: Not provided")
    print(f"--- End of Initial Log for Planner Tool ---")
    
    serialized_current_user_stops = [stop.model_dump() for stop in user_specified_stops] if user_specified_stops else []
    
    parsed_existing_base_plan = None
    previous_user_specified_stops_from_existing_plan = [] # Not directly used for merging here, but could be for complex diff. For now, previous base_plan is key.

    if existing_plan_json:
        try:
            existing_plan_data = json.loads(existing_plan_json)
            if isinstance(existing_plan_data, dict):
                parsed_existing_base_plan = existing_plan_data.get('base_plan')
                # previous_user_specified_stops_from_existing_plan = existing_plan_data.get('user_specified_stops', []) # If needed later
                if parsed_existing_base_plan:
                    print("Successfully parsed 'base_plan' from existing_plan_json.")
                else:
                    print("Warning: 'existing_plan_json' provided but 'base_plan' key was missing or empty.")
            else:
                print("Warning: 'existing_plan_json' did not parse into a dictionary.")
        except json.JSONDecodeError as e:
            print(f"Warning: Failed to parse 'existing_plan_json': {e}. Proceeding as if no existing plan was provided.")
            existing_plan_json = None # Nullify on error to prevent passing bad data
            parsed_existing_base_plan = None
        except Exception as e:
            print(f"Unexpected error processing 'existing_plan_json': {e}")
            existing_plan_json = None
            parsed_existing_base_plan = None


    output: Dict[str, Any] = {
        "travel_duration_requested": travel_duration,
        "base_plan": None, # Will be populated by result['plan']
        "user_specified_stops": serialized_current_user_stops, # Reflects stops for THIS call
        "notes": [] # Will include messages from the optimizer
    }

    try:
        # Pass the parsed_existing_base_plan and the current user_specified_stops (as deltas/overrides)
        # to the optimizer. The optimizer will handle merging/preserving.
        optimizer_result = optimize_distance_tour(
            travel_duration_str=travel_duration,
            user_specified_stops_for_modification=serialized_current_user_stops, # These are the new/changed stops
            previous_base_plan_data=parsed_existing_base_plan     # This is the plan to preserve/modify
        )
        
        # The optimizer_result is now a dict like {"plan": ..., "message": ...}
        output["base_plan"] = optimizer_result.get("plan") # This can be None if validation failed
        optimizer_message = optimizer_result.get("message", "Optimizer did not return a message.")
        output["notes"].append(f"Planner Message: {optimizer_message}")

        # Add general notes based on the outcome
        if output["base_plan"] is not None and "Successfully" in optimizer_message:
            if parsed_existing_base_plan and serialized_current_user_stops:
                output["notes"].append("Context: The existing travel plan was modified with your requested changes, provided they were valid.")
            elif parsed_existing_base_plan:
                output["notes"].append("Context: The existing travel plan was loaded. If no new specific modifications were requested or if modifications were invalid, it should reflect the previous plan.")
            elif serialized_current_user_stops:
                output["notes"].append("Context: A new travel plan has been generated, incorporating your specified stops if they were valid.")
            else:
                output["notes"].append("Context: A new base travel plan has been generated.")
        elif "Cannot" in optimizer_message or output["base_plan"] is None: # Indicates a failure in planning/modification due to invalid stop
            output["notes"].append("Action: Please review the planner message. You may need to provide a valid location in Da Nang or correct the stop details.")
        
        # Notes about user_specified_stops for this call (these are what the user *asked* for in this turn)
        if user_specified_stops: 
            output["notes"].append(
                f"User Requests This Turn: {len(user_specified_stops)} specific stop(s) were requested. Their processing outcome is reflected in the Planner Message and the resulting plan (if any)."
            )
            for stop_idx, stop_obj in enumerate(user_specified_stops):
                note = f"  - Request {stop_idx+1}: '{stop_obj.name}' for Day {stop_obj.day}, {stop_obj.time_of_day}."
                if stop_obj.address:
                    note += f" (Address provided: '{stop_obj.address}')"
                output["notes"].append(note)
        
        return json.dumps(output, indent=2, ensure_ascii=False)

    except Exception as e:
        print(f"Error during trip planning: {e}")
        traceback.print_exc()
        error_output = {
            "error": f"Failed to generate plan: {str(e)}",
            "travel_duration_requested": travel_duration,
            "user_specified_stops": serialized_current_user_stops,
            "notes": ["An error occurred during plan generation."]
        }
        if existing_plan_json:
            error_output["notes"].append("Attempted to modify an existing plan.")
        return json.dumps(error_output, indent=2, ensure_ascii=False)

# --- Flight Booking Tool ---
class FlightSearchArgs(BaseModel):
    origin_city: str = Field(description="The departure city name (e.g., 'Hanoi', 'Ho Chi Minh City').")
    date_str: str = Field(description="The desired departure date. Accepts formats like 'DD/MM/YYYY', 'Month DD, YYYY' (e.g., '19/04/2025', 'April 19, 2025'), or 'Month DD' (e.g., 'May 12'). If the year is omitted from 'Month DD', it will be interpreted for the year 2025, as flight data is specific to this year.")
    # destination_city: str = Field(description="The destination city name (Optional, currently not used for filtering).", default=None) # Add if filtering becomes possible

@tool("show_flights", args_schema=FlightSearchArgs)
def show_flights_tool(origin_city: str, date_str: str) -> str:
    """
    Searches for available flights to Da Nang (DAD) from specified Vietnamese origin cities (Hanoi - HAN, Ho Chi Minh City - SGN)
    for tomorrow and the day after tomorrow in the year 2025.
    Requires the origin city and the departure date.
    It will inform the user if data for other cities or dates is not available.
    Returns flight details as a JSON string, or an error/message string.
    """
    print(f"--- Calling Flight Tool with origin: {origin_city}, date: {date_str} ---")
    try:
        # Call the flight picking service function
        flights_result = get_flights_service(origin_city=origin_city, date_str=date_str)
        
        # The service function already returns a dictionary, which can be directly converted to JSON string.
        # It handles errors by returning a dict with an 'error' or 'message' key.
        return json.dumps(flights_result, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error in show_flights_tool: {e}")
        traceback.print_exc()
        # Return a JSON string indicating an unexpected error in the tool itself
        return json.dumps({"error": f"An unexpected error occurred while trying to get flight information: {str(e)}"})

# --- Conceptual Tool Schema for Requesting Clarification ---
class RequestClarificationArgs(BaseModel):
    missing_parameter_name: str = Field(description="The specific piece of information that is missing from the user's query, e.g., 'travel_duration', 'flight_origin_city'.")
    original_tool_name: str = Field(description="The name of the tool that the assistant intended to use before realizing information was missing, e.g., 'plan_da_nang_trip', 'show_flights'.")

# Note: There is no @tool decorator for RequestClarificationArgs because it's not a directly executable Python function.
# It's a schema to guide the LLM when it needs to "call" the conceptual 'request_clarification_tool'.

# --- Flight Selection Tool ---
class SelectFlightArgs(BaseModel):
    selection_type: str = Field(description="The method user wants to select the flight. Can be 'ordinal' (e.g., 'first', '2nd', '3'), 'flight_id' (e.g., 'VietJet Air 1634'), or 'departure_time' (e.g., '9:05 pm', '5am').")
    selection_value: str = Field(description="The specific value corresponding to the selection_type. For 'ordinal', the number or word. For 'flight_id', the flight identifier. For 'departure_time', the time string.")
    # available_flights will be passed by the agent from its state, not directly by the LLM.

# This is a wrapper. The actual call to select_flight_for_booking will happen in the agent's
# take_action method, which will retrieve available_flights from state.
# The LLM will invoke this tool with selection_type and selection_value.
# The result from select_flight_for_booking will be structured by take_action.
# So this tool function itself doesn't need to do much other than exist for the LLM.
# However, to make it a valid tool that can be 'invoked' even if its result is
# re-interpreted/augmented by take_action, it needs to run.
# We'll have it return the args, which take_action will use.

@tool("select_flight_tool", args_schema=SelectFlightArgs)
def select_flight_tool_func(selection_type: str, selection_value: str) -> str:
    """
    Use this tool when the user has been presented with a list of flights and wants to select one.
    You need to determine how the user is trying to select the flight (by its order in the list, its flight ID, or its departure time)
    and provide the corresponding value.
    For example:
    - User: "Book the first flight." -> selection_type="ordinal", selection_value="first"
    - User: "I want flight VN123." -> selection_type="flight_id", selection_value="VN123"
    - User: "The one leaving at 9pm." -> selection_type="departure_time", selection_value="9pm"
    The actual flight selection from the previously provided list happens based on these inputs.
    This tool returns a JSON string of the selection arguments, which are then processed internally.
    """
    print(f"--- select_flight_tool_func called with type: {selection_type}, value: {selection_value} ---")
    # The agent's take_action method will handle the actual call to select_flight_for_booking
    # using these arguments and the available_flights from state.
    # This tool's direct output is more of a signal with the LLM's interpreted args.
    return json.dumps({"selection_type": selection_type, "selection_value": selection_value, "message": "Selection parameters captured for processing."})

# Add more tools as needed (e.g., search_activities, check_weather, schedule_event)

# --- RAG Tool for Place/Restaurant Retrieval ---
class RAGSearchArgs(BaseModel):
    query: str = Field(description="Natural language query for finding places, restaurants, or hotels. Examples: 'top 5 restaurants in hải châu', 'find hotels near the beach', 'best cafes with high rating', 'restaurants near Fivitel Da Nang Hotel'.")

@tool("search_places_rag", args_schema=RAGSearchArgs)
def search_places_rag_tool(query: str) -> str:
    """
    Searches for places, restaurants, or hotels in Da Nang using advanced RAG (Retrieval-Augmented Generation) capabilities.
    
    This tool can handle various types of queries:
    - Location-based searches: "restaurants in hải châu district"
    - Distance-based searches: "hotels near the beach", "cafes near Fivitel Da Nang Hotel"
    - Rating-based searches: "top 5 restaurants by rating"
    - Semantic searches: "romantic dinner places", "budget-friendly accommodations"
    
    The tool automatically determines the best search strategy (keyword, distance-based, or semantic search)
    based on the query content and returns detailed information about matching places.
    
    Returns a JSON string with search results including place details like name, rating, address, 
    coordinates, and additional metadata.
    """
    print(f"--- Calling RAG Search Tool with query: '{query}' ---")
    
    try:
        retriever = RetrieverService()
        
        intent = parse_rag_intent(query)
        print(f"Parsed intent: {intent}")
        
        results = retriever.retrieve_places(intent)
        
        response = {
            "query": query,
            "intent": intent,
            "results_count": len(results),
            "results": results
        }
        
        # Add summary information
        if results:
            response["summary"] = f"Found {len(results)} places matching your query."
            if intent.get("location_ref"):
                response["summary"] += f" Results are sorted by distance from '{intent['location_ref']}'."
            elif intent.get("location_filter"):
                response["summary"] += f" Results are filtered for '{intent['location_filter']}' area."
            else:
                response["summary"] += " Results are based on semantic similarity to your query."
        else:
            response["summary"] = "No places found matching your query. Try rephrasing or using different keywords."
        
        return json.dumps(response, indent=2, ensure_ascii=False)
        
    except Exception as e:
        print(f"Error in search_places_rag_tool: {e}")
        traceback.print_exc()
        
        error_response = {
            "error": f"An error occurred while searching for places: {str(e)}",
            "query": query,
            "results_count": 0,
            "results": []
        }
        return json.dumps(error_response, indent=2, ensure_ascii=False)

def parse_rag_intent(query: str) -> Dict[str, Any]:
    """
    Uses an LLM to parse a user query and extract structured information for RAG retrieval.
    
    Args:
        query: The user's natural language query.
        
    Returns:
        A dictionary containing the parsed intent.
    """
    print(f"--- Parsing RAG intent with LLM for query: '{query}' ---")
    
    # Initialize LLM for intent parsing
    llm = ChatOpenAI(
        model=os.getenv("MODEL_VERSION"),
        temperature=0,
        api_key=os.getenv("OPENAI_API_KEY")
    )
    
    # Create the prompt for intent parsing
    intent_parsing_prompt = """You are an expert at parsing user queries about places and services in Da Nang, Vietnam.

Your task is to extract structured information from the user's query and return it as a JSON object.

Extract the following information:
1. **entity_type**: The type of place being searched for. Must be one of these exact categories:
   - tourist_attraction (for sightseeing, landmarks, monuments, viewpoints)
   - restaurant (for dining establishments)
   - cafe (for coffee shops, tea houses)
   - bar (for nightlife, pubs, lounges)
   - bakery (for bread shops, pastry shops)
   - supermarket (for grocery stores, markets)
   - shopping_mall (for malls, shopping centers)
   - store (for general retail shops)
   - souvenir_store (for gift shops, souvenir shops)
   - clothing_store (for fashion, apparel shops)
   - campground (for camping sites, glamping)
   - museum (for museums, cultural centers)
   - art_gallery (for art galleries, exhibition spaces)
   - park (for parks, gardens, green spaces)
   - zoo (for zoos, wildlife parks)
   - aquarium (for aquariums, marine centers)
   - amusement_park (for theme parks, entertainment venues)
   - stadium (for sports venues, stadiums)
   - hospital (for medical facilities)
   - pharmacy (for pharmacies, drug stores)
   - atm (for ATM locations, banks)
   - hotel (for accommodations, resorts, hostels)
   - place (for general searches or when category is unclear)

2. **top_k**: Number of results requested (default: 5)
3. **location_filter**: Specific area/district mentioned (e.g., "hai chau", "son tra", "ngu hanh son", "cam le")
4. **location_ref**: Reference location for "near X" queries (e.g., "near Dragon Bridge", "near beach")
5. **sort_by**: How to sort results (rating, distance, relevance) (default: rating)

Rules:
- Choose the most specific entity_type that matches the query
- If user asks for "near X", set location_ref to X and sort_by to "distance"
- If user asks for places "in X area", set location_filter to X and sort_by to "rating"
- If user asks for "top/best", set sort_by to "rating"
- Default entity_type is "place" if unclear
- Default top_k is 5
- Default sort_by is "relevance"

Examples:
Query: "top 5 restaurants in hai chau district"
Response: {"entity_type": "restaurant", "top_k": 5, "location_filter": "hai chau", "sort_by": "rating", "location_ref": null}

Query: "hotels near my khe beach"
Response: {"entity_type": "hotel", "top_k": 5, "location_filter": null, "sort_by": "distance", "location_ref": "my khe beach"}

Query: "best cafes with high rating"
Response: {"entity_type": "cafe", "top_k": 5, "location_filter": null, "sort_by": "rating", "location_ref": null}

Query: "museums downtown"
Response: {"entity_type": "museum", "top_k": 5, "location_filter": "downtown", "sort_by": "rating", "location_ref": null}

Query: "souvenir shops near Dragon Bridge"
Response: {"entity_type": "souvenir_store", "top_k": 5, "location_filter": null, "sort_by": "distance", "location_ref": "Dragon Bridge"}

Query: "parks for kids"
Response: {"entity_type": "park", "top_k": 5, "location_filter": null, "sort_by": "rating", "location_ref": null}

Query: "shopping malls with good stores"
Response: {"entity_type": "shopping_mall", "top_k": 5, "location_filter": null, "sort_by": "rating", "location_ref": null}

Query: "tourist attractions to visit"
Response: {"entity_type": "tourist_attraction", "top_k": 5, "location_filter": null, "sort_by": "rating", "location_ref": null}

Return ONLY the JSON object, no other text."""

    try:
        messages = [
            SystemMessage(content=intent_parsing_prompt),
            HumanMessage(content=f"Query: \"{query}\"")
        ]
        
        response = llm.invoke(messages)
        
        intent_json = json.loads(response.content.strip())
        
        intent_json["original_query"] = query.lower()
        
        print(f"LLM parsed intent: {intent_json}")
        return intent_json
        
    except Exception as e:
        print(f"Error in LLM intent parsing: {e}. Falling back to default intent.")
        return {
            "entity_type": "place",
            "top_k": 5,
            "location_filter": None,
            "sort_by": "relevance",
            "location_ref": None,
            "original_query": query.lower()
        }

