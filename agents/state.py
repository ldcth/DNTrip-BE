# state.py
from typing import TypedDict, List, Annotated, Optional
from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage
import operator

class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    relevance_decision: Optional[str]
    query_type: Optional[str]
    intent: Optional[str]