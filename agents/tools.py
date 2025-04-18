# tools.py
from langchain_core.tools import tool, StructuredTool
from pydantic import BaseModel, Field
from services.tsp_algorithm import optimize_distance_tour
from services.flight_picking import get_flights as get_flights_service # Renamed import
import json
import traceback

class TravelPlanArgs(BaseModel):
    travel_duration: str = Field(description="The duration of the trip, e.g., '3 days 2 nights', '1 week', '5 ngay 4 dem'.")

@tool("plan_da_nang_trip", args_schema=TravelPlanArgs)
def plan_da_nang_trip_tool(travel_duration: str) -> str:
    """
    Plans a detailed travel itinerary for Da Nang, Vietnam based on a specified duration.
    Generates a day-by-day plan including places to visit (like Ba Na Hills, Marble Mountains, beaches, pagodas)
    and restaurants for lunch and dinner, ensuring locations are suitable for morning, afternoon, or evening.
    The tool requires the travel duration as input (e.g., '3 days 2 nights', '1 week').
    Returns the plan as a JSON string.
    """
    print(f"--- Calling Planner Tool with duration: {travel_duration} ---")
    try:
        # Assuming optimize_distance_tour returns a dict/list serializable to JSON
        plan_result = optimize_distance_tour(travel_duration)
        # Ensure proper JSON formatting, especially for non-ASCII chars if any
        return json.dumps(plan_result, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error during trip planning: {e}")
        traceback.print_exc()
        return json.dumps({"error": f"Failed to generate plan: {e}"})

# --- Flight Booking Tool ---
class FlightSearchArgs(BaseModel):
    origin_city: str = Field(description="The departure city name (e.g., 'Hanoi', 'Ho Chi Minh City').")
    date_str: str = Field(description="The desired departure date. Use formats like DD/MM/YYYY, Month DD, YYYY (e.g., '19/04/2025', 'April 19, 2025').")
    # destination_city: str = Field(description="The destination city name (Optional, currently not used for filtering).", default=None) # Add if filtering becomes possible

@tool("book_flights", args_schema=FlightSearchArgs)
def book_flights_tool(origin_city: str, date_str: str) -> str:
    """
    Looks up available flights from a specific origin city on a given date based on locally stored data, simulating a booking lookup.
    Requires the origin city and the date. Destination is currently ignored.
    Returns a JSON string containing a list of flights (up to 10) or an error/message.
    """
    print(f"--- Calling Flight Booking Tool with Origin: {origin_city}, Date: {date_str} ---")
    try:
        # Call the actual service function (assuming it still just gets flight data)
        flight_result = get_flights_service(origin_city=origin_city, date_str=date_str)
        # Return results as a JSON string for the LLM
        return json.dumps(flight_result, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error during flight booking tool execution: {e}")
        traceback.print_exc()
        # Return error as JSON string
        return json.dumps({"error": f"An unexpected error occurred in the flight booking tool: {e}"})

# Add more tools as needed (e.g., search_activities, check_weather, schedule_event)

