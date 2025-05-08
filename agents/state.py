# state.py
from typing import TypedDict, List, Annotated, Optional, Any, Dict
from langchain_core.messages import AnyMessage
import operator

class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    relevance_decision: Optional[str]
    query_type: Optional[str]
    intent: Optional[str]
    final_response_data: Any | None = None
    final_response_tool_name: Optional[str]
    # For storing structured data like current plan or flight options
    information: Optional[Dict[str, Any]]
    # For managing clarification dialogues
    pending_clarification: Optional[Dict[str, Any]]

# Example for pending_clarification:
# {
#   "missing_arg": "trip_duration",
#   "original_intent": "plan_trip",
#   "message_to_user": "To plan your trip, I need to know how long it will be. Could you please tell me the duration?"
# }