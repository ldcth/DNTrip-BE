# tools.py
from langchain_core.tools import tool, StructuredTool
from pydantic import BaseModel, Field
from services.tsp_algorithm import optimize_distance_tour
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
        plan_result = optimize_distance_tour(travel_duration)
        return json.dumps(plan_result, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error during trip planning: {e}")
        traceback.print_exc()
        return json.dumps({"error": f"Failed to generate plan: {e}"})

# Add more tools as needed (e.g., search_activities, check_weather, schedule_event)

