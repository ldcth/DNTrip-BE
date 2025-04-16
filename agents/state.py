# state.py
from typing import TypedDict, List, Annotated
from langgraph.graph.message import add_messages

class TravelPlanState(TypedDict):
    """
    Represents the state of our travel planning graph.

    Attributes:
        messages: The history of messages in the conversation.
        plan: The current travel plan details.
        flight_info: Information about booked flights.
        hotel_info: Information about booked hotels.
        # Add other relevant fields as needed
    """
    messages: Annotated[List[tuple], add_messages]
    plan: str | None
    flight_info: dict | None
    hotel_info: dict | None
    # Example: add departure city, destination, dates etc.
    departure_city: str | None
    destination_city: str | None
    start_date: str | None
    end_date: str | None