# state.py
from typing import TypedDict, List, Annotated, Optional, Any
from langchain_core.messages import AnyMessage
import operator

class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    relevance_decision: Optional[str]
    query_type: Optional[str]
    intent: Optional[str]
    final_response_data: Any | None = None
    final_response_tool_name: Optional[str]