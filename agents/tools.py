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

