import os
import traceback
# import asyncio # Removed
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver 
from langgraph.checkpoint.mongodb import MongoDBSaver 
from pymongo import MongoClient 
from langchain_openai import ChatOpenAI
from langchain_core.messages import AnyMessage, SystemMessage, HumanMessage, ToolMessage, AIMessage
from langchain_community.tools.tavily_search import TavilySearchResults
from agents.state import AgentState
from agents.tools import plan_da_nang_trip_tool, show_flights_tool, RequestClarificationArgs, select_flight_tool_func, SelectFlightArgs
import sqlite3 # Keep for potential future use or context
import json
import logging
from services.flight_selection import select_flight_for_booking
from .history_manager import summarize_conversation_history, prune_conversation_history
from langchain.tools import StructuredTool

load_dotenv()

# sqlite_conn = sqlite3.connect("checkpoints.sqlite", check_same_thread=False)
# memory = SqliteSaver(conn=sqlite_conn)

mongodb_uri = os.getenv("MONGODB_URI")
if not mongodb_uri:
    raise ValueError("MONGODB_URI environment variable not set.")
mongo_client = MongoClient(mongodb_uri)
memory = MongoDBSaver(
    client=mongo_client,
    db_name="dntrip",
    collection_name="langgraph_checkpoints"
)

# Dummy function for the conceptual tool's schema
def _dummy_request_clarification_func(missing_parameter_name: str, original_tool_name: str):
    """This is a dummy function for schema purposes and should not be called directly."""
    # This function will not be executed by the agent's action node.
    # Its purpose is to satisfy StructuredTool.from_function requirements.
    # The actual logic is handled in the graph's routing.
    print("WARNING: _dummy_request_clarification_func was called. This should not happen.")
    return "Error: Clarification dummy function was called."

class Agent:
    def __init__(self):
        # Removed async init comments
        self.system =  """You are a smart research assistant specialized in Da Nang travel.
Use the search engine ('tavily_search_results_json') to look up specific, current information relevant to Da Nang travel (e.g., weather, specific opening hours, event details) ONLY IF the user asks for general information that isn't about flights or planning.

If the user asks for a travel plan (e.g., 'plan a 3 days 2 nights trip', 'make a plan for 1 week'):
- Use the 'plan_da_nang_trip' tool. Accurately extract the travel duration.
- If the user ALSO specifies particular places to visit at certain times (e.g., 'include Ba Na Hills on day 1 morning', 'I want to go to XYZ bookstore at 123 Main St on day 2 evening'), you MUST include these details in the 'user_specified_stops' argument for the 'plan_da_nang_trip' tool.
- For each specific stop, provide:
    - 'name': The name of the place.
    - 'day': An integer for the day number in the itinerary (e.g., 1 for Day 1).
    - 'time_of_day': A string like 'morning', 'afternoon', or 'evening'.
    - 'address': (Optional) If the user provides an address for a custom location not widely known in Da Nang, include it. Otherwise, omit.
- If the user wants to ADJUST an existing plan (e.g., "add Marble Mountains to my current plan for day 2 morning", "change my plan to include Con Market on day 1 afternoon instead of X", "I want to go to Han Market on day 1 afternoon"):
    - You have a current travel plan. The details of this plan (travel duration, and the schedule of activities) are available in the `ToolMessage` from the most recent successful 'plan_da_nang_trip' tool call. This `ToolMessage` contains a JSON string with `travel_duration_requested`, `base_plan` (which includes `daily_plans` detailing `planned_stops` for each `day` and `time_of_day`), and `user_specified_stops` (the list that was input to that tool call).
    - Identify the user's specific change: `requested_place_name`, `requested_day_number` (integer), and `requested_time_of_day` (e.g., 'morning', 'afternoon', 'evening'). Determine if it's an addition or a replacement for the targeted slot.

    - You MUST call the 'plan_da_nang_trip' tool for any adjustment.
    - **WHEN CALLING 'plan_da_nang_trip' FOR ANY ADJUSTMENT/MODIFICATION, YOUR ARGUMENTS MUST BE AS FOLLOWS:**
        - **1. `user_intention` (MANDATORY FOR MODIFICATIONS): You ABSOLUTELY MUST include the argument `user_intention: "modify"`. This is the ONLY way the system knows to modify the current plan. If this argument is set to "create" or omitted, a new plan will be generated, which is INCORRECT for a modification request.**
        - **2. `travel_duration`**: Extract this from the `travel_duration_requested` field within the parsed JSON of the previous plan's `ToolMessage`.
        - **3. `user_specified_stops` (PROVIDE ONLY THE CHANGE):** This argument should now ONLY contain a list with the single specific stop (or multiple stops if the user requests several distinct changes in one go) that the user is currently explicitly requesting to change or add.
            - For example, if the user says "I want to go to Han Market on day 1 afternoon", your `user_specified_stops` argument should be: `[{'name': 'Han Market', 'day': 1, 'time_of_day': 'afternoon'}]`.
            - If the user says "Replace Con Market with Dragon Bridge on Day 2 morning", it would be `[{'name': 'Dragon Bridge', 'day': 2, 'time_of_day': 'morning'}]`.
            - **DO NOT try to include any other stops from the previous plan in this list.** The agent system will handle merging this specific change with the existing plan.
        - **4. `existing_plan_json` (DO NOT PROVIDE FOR MODIFICATIONS): You MUST NOT include the `existing_plan_json` argument in your tool call when `user_intention: "modify"` is set. The agent system will automatically load the current plan from its memory. Providing `existing_plan_json` here will be ignored or may cause errors.**

- IMPORTANT: After a successful call to 'plan_da_nang_trip', the subsequent ToolMessage will contain the full plan details (base_plan, user_specified_stops from your input, notes) as a JSON string.
  Your response to the user MUST clearly manage expectations based on this JSON data:
  1. Present the `base_plan` day by day as suggested by the automated planner.
  2. If `user_specified_stops` are present in the JSON, list them clearly, stating what was requested (name, day, time).
  3. Refer to the `notes` section from the tool's JSON output. Based on these notes, you MUST explain that the `base_plan` is an automated suggestion.
  4. Crucially, state that the user's specific requests (`user_specified_stops`) are NOT automatically integrated into the `base_plan`'s optimized route by the current planning algorithm. The `base_plan` is generated independently.
  5. Advise the user that they should consider the `base_plan` as a starting point and may need to manually adjust it to incorporate their specific requests. For example: "Here's a suggested base itinerary. You also requested [X specific stop] for [Day Y, time]. Please note that the automated base plan is generated independently and doesn't dynamically incorporate your specific requests into its route. You may need to adjust this suggested plan to fit in [X specific stop] as desired. The base plan, for instance, suggests [mention what base plan has for that slot, if anything different]."
  Make your overall response transparent and helpful, clearly delineating between the automated suggestion and the user's specific, noted requests.

If the user asks about flights (e.g., 'show me flights to Da Nang on date', 'find flights from Hanoi to Da Nang on date'):
- First, ensure the user has provided both the ORIGIN CITY (e.g., 'Hanoi', 'Ho Chi Minh City') and the DEPARTURE DATE (e.g., 'May 12', '2025-05-12'). 
- If user's query have both origin city and date, you can directly use the 'show_flight' tool.
- If EITHER the origin city OR the date is missing or unclear from the user's query, you MUST use the 'request_clarification_tool' to ask for the missing information (e.g., 'missing_parameter_name': 'flight_origin_city' or 'missing_parameter_name': 'flight_date'). Do NOT guess or assume these values.
- Once you have both origin and date, use the 'show_flight' tool. This tool will find available flights and they will be stored internally for selection.
- After the 'show_flight' tool successfully finds and stores flights (you will know this from the ToolMessage content like "I found X flights..."), your direct response to the user should ONLY be that confirmation message from the tool (e.g., "I found X flights for you from [Origin] on [Date]. Which one would you like to select?"). DO NOT list the flight details yourself at this stage. Then, WAIT for the user to make a selection.

After flight options have been found by 'show_flight' and you have relayed the confirmation message to the user, if the user then indicates a choice (e.g., "the first one", "book flight X", "the one at 9pm"), you MUST use the 'select_flight_tool'.
- You must determine the selection_type ('ordinal', 'flight_id', or 'departure_time') and the corresponding selection_value from the user's request for 'select_flight_tool'.
- If 'select_flight_tool' is successful (you will know this from the ToolMessage content like "Successfully selected flight..."), your response to the user should be a natural language confirmation based on the details from that ToolMessage (e.g., "Okay, I have selected flight [Flight ID] for you. It departs at [Time] and costs [Price].").

When essential information for using ANY tool is missing (including for 'select_flight_tool' if the selection criteria are unclear after flights have been presented),
DO NOT attempt to use the tool with incomplete information or guess the missing details.
Instead, you MUST call the 'request_clarification_tool'.
When calling 'request_clarification_tool', provide the following arguments:
- 'missing_parameter_name': A string describing the specific piece of information that is missing (e.g., 'travel_duration', 'flight_origin_city', 'flight_date', 'flight_selection_details', 'user_specified_stops_detail').
- 'original_tool_name': The name of the tool you intended to use (e.g., 'plan_da_nang_trip', 'show_flight', 'select_flight_tool').

Answer questions ONLY if they are related to travel in Da Nang, Vietnam, including flights *originating* from other Vietnamese cities TO Da Nang (if data exists).
If a query is relevant but doesn't require planning, flight booking, flight selection, or external web search, answer directly from your knowledge.
If a query is irrelevant (not about Da Nang travel, flights to/from relevant locations, or planning), politely decline.
"""
        self.llm = ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0,
                api_key=os.getenv("OPENAI_API_KEY")
            )
        self.tavily_search = TavilySearchResults(max_results=2)
        self.planner_tool = plan_da_nang_trip_tool
        self.flight_tool = show_flights_tool
        self.select_flight_tool = select_flight_tool_func

        # Define the conceptual tool for clarification using its Pydantic schema
        self.request_clarification_tool = StructuredTool.from_function(
            func=_dummy_request_clarification_func, # Use the dummy function
            name="request_clarification_tool",
            description="Use this tool to ask the user for missing information required by another tool.",
            args_schema=RequestClarificationArgs
        )

        self.model = self.llm.bind_tools([
            self.tavily_search, 
            self.planner_tool, 
            self.flight_tool,
            self.select_flight_tool,
            self.request_clarification_tool
        ])

        self.router_llm = ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0,
                api_key=os.getenv("OPENAI_API_KEY")
            )

        self.graph = StateGraph(AgentState)
        self.graph.add_node("initial_router", self.initial_router)
        self.graph.add_node("direct_llm_answer", self.direct_llm_answer)
        self.graph.add_node("relevance_checker", self.check_relevance)
        self.graph.add_node("intent_router", self.route_intent)
        self.graph.add_node("call_llm_with_tools", self.call_llm_with_tools)
        self.graph.add_node("action", self.take_action)
        self.graph.add_node("mark_not_related", self.mark_not_related_node)
        self.graph.add_node("clarification_node", self.clarification_node)
        self.graph.add_node("retrieve_stored_information", self.retrieve_stored_information)

        self.graph.set_entry_point("initial_router")
        self.graph.add_conditional_edges(
            "initial_router",
            self.route_based_on_query_type,
            {
                "persona": "direct_llm_answer",
                "history": "direct_llm_answer",
                "content": "relevance_checker"
            }
        )
        self.graph.add_conditional_edges(
            "relevance_checker",
            self.route_based_on_relevance,
            {
                "continue": "intent_router",
                "end": "mark_not_related"
            }
        )
        self.graph.add_conditional_edges(
            "intent_router",
            self.route_based_on_intent,
            {
                "plan_agent": "call_llm_with_tools",
                "flight_agent": "call_llm_with_tools",
                "information_agent": "call_llm_with_tools",
                "retrieve_information": "retrieve_stored_information",
                "general_qa_agent": "call_llm_with_tools",
                "error": END
            }
        )
        self.graph.add_conditional_edges(
            "call_llm_with_tools",
            self.route_after_llm_call,
            {
                "clarification_node": "clarification_node",
                "action": "action",
                END: END
            }
        )
        self.graph.add_edge("direct_llm_answer", END)
        self.graph.add_edge("mark_not_related", END)
        self.graph.add_edge("clarification_node", END)
        self.graph.add_edge("retrieve_stored_information", END)

        self.graph.add_conditional_edges(
            "action",
            self.route_after_action,
            {
                "finish": END,
                "continue": "call_llm_with_tools"
            }
        )

        self.memory = memory
        self.graph = self.graph.compile(checkpointer=self.memory)
        # Add the conceptual tool name to self.tools dict; it won't have a callable function here.
        self.tools = {t.name: t for t in [self.tavily_search, self.planner_tool, self.flight_tool, self.select_flight_tool]}
        self.tools[self.request_clarification_tool.name] = None # Store by its actual name, still no function

    def initial_router(self, state: AgentState):
        """Routes the query based on its type."""
        user_message = state['messages'][-1]
        if not isinstance(user_message, HumanMessage):
             print("Warning: Expected last message to be HumanMessage for initial routing.")
             return {"query_type": "content", "relevance_decision": None, "intent": None}

        routing_prompt = SystemMessage(content="""Classify the following user query into one of these categories:
- 'persona': Questions about the bot's identity or capabilities (e.g., 'Who are you?', 'What can you do?')
- 'history': Questions ONLY about the sequence or flow of the conversation itself (e.g., 'What did I ask you last?', 'Summarize our chat'). Do NOT use this for requests to *recall* information previously discussed.
- 'content': Any other type of question, including travel planning, flight searches, general info requests, OR requests to *recall* or *repeat* information previously provided (e.g., 'show me the plan again', 'what were those flights?').
Respond only with the category name.""")

        try:
            # print(f"Full message 123123: {state['messages']}")
            response = self.router_llm.invoke([routing_prompt, user_message])
            # Strip whitespace, lowercase, AND strip potential quotes
            query_type = response.content.strip().lower().strip('\'"') 
            print(f"Initial routing for query '{user_message.content[:50]}...': {query_type}")
        except Exception as e:
             print(f"Error during initial routing: {e}")
             traceback.print_exc()
             query_type = "content"

        return {"query_type": query_type, "relevance_decision": None, "intent": None}

    def route_based_on_query_type(self, state: AgentState):
        """Validates query_type in state and RETURNS the routing decision string."""
        query_type = state.get("query_type")
        # print(f"--- route_based_on_query_type (validation) --- State received: {state}") # Keep logging if needed
        validated_query_type = "content" # Default
        if query_type:
             # print(f"Query type from initial_router: {query_type}") # Keep logging if needed
             if query_type in ["persona", "history", "content"]:
                 validated_query_type = query_type
             else:
                 print(f"Warning: Unexpected query_type '{query_type}' found in route_based_on_query_type. Defaulting to 'content'.")
        else:
             print("Warning: Query type not found in state. Defaulting to 'content'.")
        
        # Return the validated string directly for routing
        print(f"--- route_based_on_query_type --- Returning decision: {validated_query_type}")
        return validated_query_type 
        # Old version that just updated state:
        # return {"query_type": validated_query_type}

    def direct_llm_answer(self, state: AgentState):
        """Answers persona or history questions directly using the main LLM (without tools bound initially)."""
        messages = state['messages']

        # <<< APPLY HISTORY MANAGEMENT HERE TOO >>>
        # Option 1: Summarization
        messages = summarize_conversation_history(messages, self.llm) # Pass the appropriate LLM instance
        # Option 2: Pruning
        # messages = prune_conversation_history(messages)

        # Ensure system prompt if needed (your existing logic)
        if not any(isinstance(m, SystemMessage) for m in messages):
             messages = [SystemMessage(content=self.system)] + messages

        message = self.model.invoke(messages)
        return {'messages': [message]}

    def check_relevance(self, state: AgentState):
        """Checks if the user query is related to Da Nang travel, considering recent conversation history."""
        print("--- Checking Relevance (with history) ---")
        
        # ADDED DEBUG LOGGING
        information_at_relevance_check_start = state.get("information", {})
        # Log keys and whether they have non-None/non-empty data
        info_status = {}
        for k, v in information_at_relevance_check_start.items():
            if isinstance(v, (list, dict)):
                info_status[k] = f"len={len(v)}"
            elif v is not None:
                info_status[k] = "present"
            else:
                info_status[k] = "empty/None"
        print(f"DEBUG: information status at start of check_relevance: {info_status}")

        # Prepare the full information state as a string for the LLM prompt
        info_state_string = "Current relevant information stored: " + (
            json.dumps(information_at_relevance_check_start, indent=2, ensure_ascii=False) 
            if information_at_relevance_check_start 
            else "None"
        )
        # Limit string length for prompt to avoid excessive size
        MAX_INFO_STRING_LEN = 1000 
        if len(info_state_string) > MAX_INFO_STRING_LEN:
            info_state_string = info_state_string[:MAX_INFO_STRING_LEN] + "... (truncated due to length)"

        # Define how many recent messages to include as context (includes the current user message)
        HISTORY_CONTEXT_SIZE = 5 

        if not state['messages']:
            print("Error: No messages in state for relevance check.")
            return {"relevance_decision": "end"}

        current_user_message_for_logging = state['messages'][-1]
        start_index = max(0, len(state['messages']) - HISTORY_CONTEXT_SIZE)
        history_selection_for_llm = state['messages'][start_index:]

        first_valid_idx = 0
        if history_selection_for_llm:
            for idx, msg in enumerate(history_selection_for_llm):
                if not isinstance(msg, ToolMessage):
                    first_valid_idx = idx
                    break
                if idx == len(history_selection_for_llm) - 1 and isinstance(msg, ToolMessage):
                    first_valid_idx = len(history_selection_for_llm)
        processed_history_for_llm = history_selection_for_llm[first_valid_idx:]

        if not processed_history_for_llm and isinstance(state['messages'][-1], HumanMessage):
            processed_history_for_llm = [state['messages'][-1]]

        relevance_prompt_system_message = SystemMessage(
            content=f"""Analyze the provided conversation history (if any), the LATEST user query, AND the currently stored information.
Currently Stored Information: 
```json
{info_status}
```
(This shows the full data like 'available_flights', 'confirmed_booking_details', or 'current_trip_plan' currently in memory. It might be truncated if very large.)

Your goal is to determine if the LATEST USER QUERY is relevant to Da Nang travel, considering the conversation context and stored information.

Specifically, the LATEST USER QUERY IS RELEVANT (respond 'continue') if it:
1. Directly asks about travel IN or TO Da Nang, Vietnam (e.g., planning, flights, attractions, general info or weather about Da Nang).
2. Is a direct response to a question the assistant just asked.
3. Is an action or selection related to options the assistant just presented.
4. Is a request to recall, review, or see information previously stored or confirmed (e.g., 'show my booked flight', 'what was the plan?').
5. Relates directly to the data shown in the 'Currently Stored Information' above.

The LATEST USER QUERY IS NOT RELEVANT (respond 'end') if it introduces a topic clearly outside of Da Nang travel AND is not a direct follow-up to an assistant's question, presented options, or the stored information.

IMPORTANT: Your response MUST be ONLY the single word 'continue' or the single word 'end'. Do NOT provide any other text, explanation, or formatting.
Respond only with the single word 'continue' or 'end'."""
        )

        messages_for_llm = [relevance_prompt_system_message] + processed_history_for_llm
        print(f"Messages for relevance check LLM (types): {[msg.type for msg in messages_for_llm]}")

        try:
            response = self.router_llm.invoke(messages_for_llm)
            decision = response.content.strip().lower()
            # Use current_user_message_for_logging for logging the query content itself
            print(f"Relevance check for query '{str(current_user_message_for_logging.content)[:50]}...' (with history): {decision}")
            if decision not in ["continue", "end"]:
                print(f"Warning: Relevance check returned unexpected value: {decision}. Defaulting to 'end'.")
                decision = "end"
        except Exception as e:
            print(f"Error during relevance check (with history): {e}")
            traceback.print_exc()
            decision = "end"

        return {"relevance_decision": decision}

    def route_based_on_relevance(self, state: AgentState):
        """Reads the decision from the state and returns the next node."""
        decision = state.get("relevance_decision")
        if decision:
             print(f"Routing based on relevance decision: {decision}")
             return decision
        else:
             print("Warning: Relevance decision not found in state. Defaulting to 'end'.")
             return "end"

    def route_intent(self, state: AgentState):
        """Classifies the user's intent after relevance check."""
        print("--- Routing Intent ---")

        # Check for follow-up to clarification first
        # A full clarification sequence that leads to the current HumanMessage would look like:
        # ... -> AIMessage (calls request_clarification_tool, ID: X) [index -4]
        #     -> ToolMessage (acknowledges tool_call_id X)        [index -3]
        #     -> AIMessage (natural question to user)               [index -2]
        #     -> HumanMessage (current message, user's answer)      [index -1]
        
        if len(state['messages']) >= 4:
            current_human_message = state['messages'][-1]
            ai_question_message = state['messages'][-2]
            tool_ack_message = state['messages'][-3]
            ai_tool_call_message = state['messages'][-4]

            if isinstance(current_human_message, HumanMessage) and \
               isinstance(ai_question_message, AIMessage) and \
               isinstance(tool_ack_message, ToolMessage) and tool_ack_message.tool_call_id and \
               isinstance(ai_tool_call_message, AIMessage) and ai_tool_call_message.tool_calls:
                
                for tc in ai_tool_call_message.tool_calls:
                    # Check if the ToolMessage acknowledges the tool call from the AIMessage
                    if tc.get('id') == tool_ack_message.tool_call_id and \
                       tc.get('name') == self.request_clarification_tool.name:
                        
                        original_tool_name = tc.get('args', {}).get('original_tool_name')
                        if original_tool_name == 'show_flights':
                            print(f"Intent determined as follow-up to 'show_flights' clarification. Routing to flight_agent.")
                            return {"intent": "flight_agent"}
                        elif original_tool_name == 'plan_da_nang_trip':
                            print(f"Intent determined as follow-up to 'plan_da_nang_trip' clarification. Routing to plan_agent.")
                            return {"intent": "plan_agent"}
                        elif original_tool_name == 'select_flight_tool': # select_flight_tool is part of flight_agent flow
                            print(f"Intent determined as follow-up to 'select_flight_tool' clarification. Routing to flight_agent.")
                            return {"intent": "flight_agent"}
                        # Add other original_tool_names if needed for specific routing
                        break # Found the relevant tool call and processed it

        # If not a direct follow-up to a tracked clarification, proceed with LLM-based intent classification
        user_message = state['messages'][-1]
        if not isinstance(user_message, HumanMessage):
            print("Warning: Expected last message to be HumanMessage for LLM-based intent routing.")
            return {"intent": "error"}

        # Updated intent prompt to guide flight selection queries better
        intent_prompt_text = """Given the user query (which is relevant to Da Nang travel), classify the primary intent:
- 'plan_agent': User wants to create a NEW travel plan/itinerary for Da Nang (e.g., 'plan a 3 day trip to Da Nang', 'make an itinerary') OR wants to MODIFY an EXISTING travel plan (e.g., 'change my plan to include X', 'add Y to day 1 morning', 'can you replace Z on day 2 afternoon with W?', 'I want to go to Fahasa bookstore instead of the current evening activity on day 2').
- 'flight_agent': User is asking about flights, potentially to or from Da Nang (e.g., 'flights from Hanoi?', 'show flights on date', 'book a flight from Saigon?', 'select the first flight', 'the one at 9pm').
- 'information_agent': User is asking a question likely requiring external, up-to-date information about Da Nang (weather, opening hours, specific events, prices) that isn't about flights or planning.
- 'retrieve_information': User is asking to see information the assistant has previously provided or confirmed, like a booked flight, the list of available flights shown earlier, or the current travel plan (e.g., 'show me my booked flight', 'what were those flights again?', 'can I see the plan?').
- 'general_qa_agent': User is asking a general question about Da Nang that might be answerable from general knowledge or conversation history, without needing specific tools or stored information retrieval.
Respond only with 'plan_agent', 'flight_agent', 'information_agent', 'retrieve_information', or 'general_qa_agent'."""
        intent_prompt = SystemMessage(content=intent_prompt_text)

        try:
            response = self.router_llm.invoke([intent_prompt, user_message])
            intent = response.content.strip().lower()
            print(f"LLM-based intent routing for query '{user_message.content[:50]}...': {intent}")
            valid_intents = ["plan_agent", "flight_agent", "information_agent", "retrieve_information", "general_qa_agent"]
            if intent not in valid_intents:
                print(f"Warning: LLM-based intent routing returned unexpected value: {intent}. Defaulting to 'general_qa_agent'.")
                intent = "general_qa_agent"
        except Exception as e:
             print(f"Error during LLM-based intent routing: {e}")
             traceback.print_exc()
             intent = "error"

        return {"intent": intent}

    def route_based_on_intent(self, state: AgentState):
        """Returns the classification result."""
        intent = state.get("intent")
        valid_intents = {'plan_agent', 'flight_agent', 'information_agent', 'retrieve_information', 'general_qa_agent'}
        if intent not in valid_intents:
            print(f"Warning: Unrecognized intent '{intent}'. Routing to general QA.")
            return "general_qa_agent"
        print(f"Routing based on intent: {intent}")
        return intent

    def call_llm_with_tools(self, state: AgentState):
        """Calls the main LLM bound with all relevant tools."""
        print("--- Calling LLM with Tools ---")
        current_messages = state['messages'] # Raw messages from state for this turn

        message_to_send_to_model: list[AnyMessage]
        system_message_to_use = SystemMessage(content=self.system)

        # New logic for constructing message history:
        # Get the last 5 human-initiated interactions.
        # An interaction starts with a HumanMessage and includes all subsequent AI/Tool messages
        # until the next HumanMessage or the start of the history.
        
        # max_human_interactions = 5
        # human_interaction_counter = 0
        # history_slice = [] # This will store the selected part of current_messages in correct order

        # # Iterate through current_messages in reverse to find the latest interactions
        # for message in reversed(current_messages):
        #     # Skip any SystemMessage found in the history, as we are prepending system_message_to_use.
        #     if isinstance(message, SystemMessage):
        #         continue 
            
        #     history_slice.insert(0, message) # Add to the beginning to maintain chronological order
            
        #     if isinstance(message, HumanMessage):
        #         human_interaction_counter += 1
        #         if human_interaction_counter >= max_human_interactions:
        #             break # Stop once we have enough interactions
        
        # message_to_send_to_model = [system_message_to_use] + history_slice

        message_to_send_to_model = current_messages

        print("Messages being sent to LLM:")
        for msg_idx, msg in enumerate(message_to_send_to_model):
            print(f"  - Index: {msg_idx}, Type: {type(msg).__name__}")
            if isinstance(msg, ToolMessage):
                 print(f"    Tool Call ID: {msg.tool_call_id}")
                 print(f"    Tool Name: {msg.name}")
                 content_str = str(msg.content)
                 print(f"    Tool Content: {content_str[:200]}{'...' if len(content_str) > 200 else ''}")
            elif isinstance(msg, AIMessage) and msg.tool_calls:
                 # For AIMessage with tool_calls, content might be empty or a short thought.
                 content_preview = str(msg.content).replace('\\n', ' ')[:100] 
                 print(f"    Content: {content_preview}...")
                 print(f"    Tool Calls: {msg.tool_calls}")
            else:
                 content_preview = str(msg.content).replace('\\n', ' ')[:100]
                 print(f"    Content: {content_preview}...")

        print(f"Calling model with {len(message_to_send_to_model)} messages: {[m.type for m in message_to_send_to_model]}")
        llm_response_message = self.model.invoke(message_to_send_to_model)
        print(f"LLM response type: {llm_response_message.type}")
        if hasattr(llm_response_message, 'tool_calls') and llm_response_message.tool_calls:
             print(f"LLM requested tool calls: {llm_response_message.tool_calls}")
        else:
             print("LLM did not request tool calls.")

        return {'messages': [llm_response_message]}

    def route_after_llm_call(self, state: AgentState):
        """Routes to clarification, action, or ends the turn after LLM tool call attempt."""
        print("--- Routing after LLM Call with Tools ---")
        last_message = state['messages'][-1]

        if not isinstance(last_message, AIMessage):
            print("Warning: Expected last message to be AIMessage in route_after_llm_call. Ending turn.")
            return END

        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            print(f"LLM produced tool calls: {last_message.tool_calls}") 
            for tool_call in last_message.tool_calls:
                tool_name = tool_call.get('name')
                tool_args = tool_call.get('args', {})
                print(f"  - Analyzing tool call: Name='{tool_name}', Args='{tool_args}'")

                if tool_name == self.request_clarification_tool.name:
                    print(f"LLM requested clarification via {self.request_clarification_tool.name}: {tool_args}. Routing to clarification_node.")
                    # DO NOT set state['pending_clarification'] here anymore.
                    # clarification_node will extract args from the AIMessage directly.
                    return "clarification_node"
            
            if any(tc.get('name') != self.request_clarification_tool.name for tc in last_message.tool_calls):
                print("Actionable tool(s) called by LLM, routing to 'action' node.")
                return "action"
        else:
            print("LLM did not produce any tool calls.")

        print("No actionable tools called by LLM or LLM provided a direct answer. Ending turn or processing direct answer.")
        return END

    def _get_natural_clarification_question(self, original_tool_name: str, missing_parameter_name: str) -> str:
        """Generates a more natural-sounding clarification question using an LLM."""
        print(f"--- Generating natural clarification question for tool: {original_tool_name}, missing: {missing_parameter_name} ---")
        
        prompt_messages = [
            SystemMessage(
                content="""You are a helpful assistant. Your task is to rephrase a templated clarification question into a more natural, polite, and conversational question for the user. 
                Do NOT be overly verbose. Keep it concise and friendly.
                The user was trying to use a specific tool, and a piece of information is missing.
                
                Example 1:
                Original Tool: 'plan_da_nang_trip'
                Missing Parameter: 'travel_duration'
                Natural Question: "To help plan your trip to Da Nang, could you let me know how long you'll be staying?"

                Example 2:
                Original Tool: 'show_flight'
                Missing Parameter: 'flight_origin_city'
                Natural Question: "I can help you with flights! What city will you be departing from?"
                
                Example 3:
                Original Tool: 'show_flight'
                Missing Parameter: 'flight_date'
                Natural Question: "Sure, I can look up flights for you. What date are you planning to travel?"
                """
            ),
            HumanMessage(
                content=f"Original Tool: '{original_tool_name}'\nMissing Parameter: '{missing_parameter_name}'\nGenerate a natural question:"
            )
        ]
        
        try:
            response = self.router_llm.invoke(prompt_messages) # Use invoke for synchronous
            natural_question = response.content.strip()
            print(f"Generated natural question: {natural_question}")
            return natural_question
        except Exception as e:
            print(f"Error generating natural clarification question: {e}. Falling back to template.")
            return f"To help me with {original_tool_name}, I need a bit more information. Could you please provide the {missing_parameter_name}?"

    def clarification_node(self, state: AgentState):
        """Generates a clarification question to the user AND a ToolMessage to acknowledge the clarification request."""
        print("--- Clarification Node ---")
        
        last_ai_message = state['messages'][-1]
        tool_call_id_to_respond_to = None
        found_tool_args = None

        if isinstance(last_ai_message, AIMessage) and hasattr(last_ai_message, 'tool_calls') and last_ai_message.tool_calls:
            for tc in last_ai_message.tool_calls:
                if tc.get('name') == self.request_clarification_tool.name:
                    tool_call_id_to_respond_to = tc.get('id')
                    found_tool_args = tc.get('args', {})
                    print(f"Clarification node found request_clarification_tool call. ID: {tool_call_id_to_respond_to}, Args: {found_tool_args}")
                    break 
        
        if not tool_call_id_to_respond_to or not found_tool_args:
            print("CRITICAL WARNING: Clarification node reached, but could not find request_clarification_tool call_id or args in the last AIMessage.")
            return {'messages': [AIMessage(content="I need more details, but encountered an internal hiccup. Could you try rephrasing?")]}

        missing_param = found_tool_args.get("missing_parameter_name", "some specific details")
        original_tool = found_tool_args.get("original_tool_name", "your request")

        question_to_user = self._get_natural_clarification_question(original_tool, missing_param) # Synchronous call
        
        tool_response_message = ToolMessage(
            content=f"Clarification for {original_tool} regarding {missing_param} is being requested from the user.",
            tool_call_id=tool_call_id_to_respond_to
        )
        
        ai_question_message = AIMessage(content=question_to_user)

        return {'messages': [tool_response_message, ai_question_message]}

    def take_action(self, state: AgentState):
        """Executes tools based on the LLM's request.
        
        Update for flight selection:
        - 'show_flight' now stores results in state['information']['available_flights'] if successful.
          The ToolMessage content should be a summary, NOT the flight list.
        - 'select_flight_tool' uses state['information']['available_flights'] and if successful,
          stores selected flight in final_response_data and its ToolMessage should confirm the specific flight.
        """
        last_message = state['messages'][-1]

        if not (isinstance(last_message, AIMessage) and
                hasattr(last_message, 'tool_calls') and
                isinstance(last_message.tool_calls, list) and
                len(last_message.tool_calls) > 0):
             print("Error: take_action called unexpectedly. Last message doesn't have valid tool calls.")
             return {'messages': [ToolMessage(tool_call_id="error", name="error", content="Internal error: Agent tried to take action without a valid tool call.")]}

        tool_calls = last_message.tool_calls
        tool_messages_to_return = []
        current_final_data = state.get('final_response_data')
        current_final_tool_name = state.get('final_response_tool_name')
        current_information = state.get('information') if state.get('information') is not None else {}

        for t in tool_calls:
            tool_call_id = t.get('id')
            if not tool_call_id:
                print(f"Warning: Tool call missing 'id': {t}. Skipping.")
                continue

            tool_name = t.get('name')
            tool_args = t.get('args', {})
            print(f"Attempting to call tool: {tool_name} with args: {tool_args} (Call ID: {tool_call_id})")
            result_content_for_message = f"Error: Tool {tool_name} execution failed." # Default

            if tool_name == self.select_flight_tool.name:
                print(f"Processing '{self.select_flight_tool.name}'...")
                available_flights = current_information.get('available_flights')
                if not available_flights or not isinstance(available_flights, list):
                    result_content_for_message = "Error: No available flights found in my memory to select from. Please search for flights first."
                    print(f"Error for {tool_name}: {result_content_for_message}")
                    current_final_data = None # Ensure no final data on error
                    current_final_tool_name = None
                else:
                    selection_type = tool_args.get('selection_type')
                    selection_value = tool_args.get('selection_value')
                    if not selection_type or not selection_value:
                        result_content_for_message = "Error: Missing 'selection_type' or 'selection_value' for selecting a flight."
                        print(f"Error for {tool_name}: {result_content_for_message}")
                        current_final_data = None
                        current_final_tool_name = None
                    else:
                        try:
                            print(f"Calling select_flight_for_booking with type='{selection_type}', value='{selection_value}', and {len(available_flights)} available flights.")
                            selection_result = select_flight_for_booking(
                                available_flights=available_flights,
                                selection_type=selection_type,
                                selection_value=selection_value
                            )
                            print(f"Result from select_flight_for_booking: {selection_result}")

                            if selection_result.get("status") == "success":
                                selected_flight = selection_result.get("flight")
                                current_final_data = selected_flight
                                current_final_tool_name = "confirmed_flight_selection"
                                flight_id = selected_flight.get('flight_id', 'N/A')
                                dep_time = selected_flight.get('departure_time', 'N/A')
                                price = selected_flight.get('price', 'N/A')
                                result_content_for_message = f"Successfully selected flight: {flight_id}, departing at {dep_time}, price {price}."
                                current_information['confirmed_booking_details'] = selected_flight
                                # current_information.pop('available_flights', None)
                                current_information['flight_search_completed_awaiting_selection'] = False
                            else:
                                result_content_for_message = selection_result.get("message", "Could not select the flight.")
                                current_final_data = None
                                current_final_tool_name = None
                        except Exception as e:
                            print(f"Exception during select_flight_for_booking call: {e}")
                            traceback.print_exc()
                            result_content_for_message = f"An error occurred while trying to select the flight: {e}"
                            current_final_data = None
                            current_final_tool_name = None
                tool_messages_to_return.append(ToolMessage(tool_call_id=tool_call_id, name=tool_name, content=result_content_for_message))

            elif tool_name in self.tools:
                tool_to_use = self.tools[tool_name]
                raw_result = None
                try:
                    # --- MODIFICATION FOR PLANNER TOOL ---
                    if tool_name == self.planner_tool.name:
                        attempting_modification = False
                        # Check for explicit modification intent first
                        if tool_args.get('user_intention') == "modify":
                            attempting_modification = True
                            print(f"Planner modification: 'user_intention' is 'modify'. Proceeding with state injection.")
                        # Heuristic: if LLM forgets user_intention='modify' but provides existing_plan_json AND we have a plan in state
                        elif tool_args.get('user_intention') != "create" and 'existing_plan_json' in tool_args and current_information.get('current_trip_plan'):
                            attempting_modification = True
                            print(f"Planner modification HEURISTIC: LLM provided 'existing_plan_json' (and intent was not explicitly 'create') and state has a plan. Forcing state injection.")

                        if attempting_modification:
                            # Pop whatever existing_plan_json the LLM might have sent (could be bad/truncated)
                            if 'existing_plan_json' in tool_args:
                                print(f"Popping 'existing_plan_json' from LLM-provided args (length: {len(tool_args['existing_plan_json']) if tool_args.get('existing_plan_json') else 0}).")
                                tool_args.pop('existing_plan_json', None)
                            
                            current_plan_from_state = current_information.get('current_trip_plan')
                            if current_plan_from_state and isinstance(current_plan_from_state, dict):
                                try:
                                    tool_args['existing_plan_json'] = json.dumps(current_plan_from_state)
                                    print(f"Successfully serialized and injected existing plan from state into tool_args. Length: {len(tool_args['existing_plan_json'])}")
                                except Exception as e:
                                    print(f"Error serializing current_trip_plan from state: {e}. Setting existing_plan_json to None.")
                                    tool_args['existing_plan_json'] = None 
                            else:
                                print("Warning: Modification attempt, but no valid 'current_trip_plan' in state. Setting existing_plan_json to None.")
                                tool_args['existing_plan_json'] = None
                            
                        # Always remove user_intention from tool_args if it was present, 
                        # as the plan_da_nang_trip_tool function itself doesn't use it directly for its core logic.
                        # Its behavior is driven by the presence/absence of existing_plan_json.
                        if 'user_intention' in tool_args:
                            print(f"Removing 'user_intention' from tool_args before calling the tool. Value was: {tool_args['user_intention']}")
                            tool_args.pop('user_intention', None)
                        
                        print(f"Planner logic complete. Final tool_args keys for tool call: {list(tool_args.keys())}")
                    
                    if isinstance(tool_args, dict):
                        raw_result = tool_to_use.invoke(tool_args)
                    else:
                         raw_result = tool_to_use.invoke(tool_args) # Should be dict, but attempt

                    if tool_name == self.flight_tool.name: # 'show_flight'
                        try:
                            parsed_data = json.loads(raw_result)
                            if isinstance(parsed_data, dict) and 'flights' in parsed_data and isinstance(parsed_data['flights'], list):
                                flight_list = parsed_data['flights']
                                if flight_list:
                                    print(f"Storing {len(flight_list)} flights in state['information']['available_flights']")
                                    current_information['available_flights'] = flight_list
                                    origin = tool_args.get('origin_city', 'your specified origin')
                                    date = tool_args.get('date_str', 'the specified date')
                                    result_content_for_message = f"I found {len(flight_list)} flights for you from {origin} to Da Nang on {date}. Which one would you like to select?"
                                    current_information['flight_search_completed_awaiting_selection'] = True
                                    current_final_data = result_content_for_message
                                    current_final_tool_name = "flights_found_summary"
                                else: # No flights in the list
                                    result_content_for_message = parsed_data.get('message', "No flights found matching your criteria.")
                                    current_information.pop('available_flights', None)
                                    current_information['flight_search_completed_awaiting_selection'] = False
                                    current_final_data = result_content_for_message
                                    current_final_tool_name = "flights_not_found_summary"
                            elif isinstance(parsed_data, dict) and ('error' in parsed_data or 'message' in parsed_data):
                                result_content_for_message = parsed_data.get('error') or parsed_data.get('message')
                                current_information.pop('available_flights', None)
                                current_information['flight_search_completed_awaiting_selection'] = False
                                current_final_data = result_content_for_message
                                current_final_tool_name = "flights_tool_error_or_message"
                            else: # Unexpected structure
                                result_content_for_message = "Received an unexpected format for flight data. I couldn't process it."
                                current_information.pop('available_flights', None)
                                current_information['flight_search_completed_awaiting_selection'] = False
                                current_final_data = result_content_for_message
                                current_final_tool_name = "flights_tool_format_error"
                        except json.JSONDecodeError:
                            result_content_for_message = f"The flight information service returned data in an unexpected format (not JSON): {raw_result[:100]}"
                            current_information.pop('available_flights', None)
                            current_information['flight_search_completed_awaiting_selection'] = False
                            current_final_data = result_content_for_message
                            current_final_tool_name = "flights_tool_format_error"
                        except Exception as format_err:
                             result_content_for_message = f"An error occurred while processing flight data: {format_err}"
                             current_information.pop('available_flights', None)
                             current_information['flight_search_completed_awaiting_selection'] = False
                             current_final_data = result_content_for_message
                             current_final_tool_name = "flights_tool_processing_error"
                        tool_messages_to_return.append(ToolMessage(tool_call_id=tool_call_id, name=tool_name, content=result_content_for_message))
                    
                    elif tool_name == self.planner_tool.name: # 'plan_da_nang_trip'
                        # raw_result is the JSON string from the tool
                        try:
                            # Try to parse it to validate and store structured data
                            parsed_data = json.loads(raw_result)
                            if isinstance(parsed_data, dict) and parsed_data and not parsed_data.get('error'):
                                current_final_data = parsed_data 
                                current_final_tool_name = tool_name
                                current_information['current_trip_plan'] = parsed_data
                                # The content for the ToolMessage should be the raw_result (the full JSON string from the tool)
                                # so the subsequent LLM call has all details to formulate a user-facing message.
                                result_content_for_message = raw_result 
                            elif isinstance(parsed_data, dict) and ('error' in parsed_data or 'message' in parsed_data):
                                result_content_for_message = parsed_data.get('error') or parsed_data.get('message')
                                current_final_data = None 
                                current_final_tool_name = None
                            else: # Should not happen if tool returns valid JSON or JSON error string
                                result_content_for_message = raw_result 
                                current_final_data = None
                                current_final_tool_name = None
                        except json.JSONDecodeError: # If raw_result is not valid JSON (e.g. plain error string from tool unexpectedly)
                            result_content_for_message = raw_result 
                            current_final_data = None
                            current_final_tool_name = None
                        except Exception as format_err: # Catch other potential errors during parsing/handling
                             result_content_for_message = f"Error processing {tool_name} results: {format_err}"
                             current_final_data = None
                             current_final_tool_name = None
                        tool_messages_to_return.append(ToolMessage(tool_call_id=tool_call_id, name=tool_name, content=result_content_for_message))

                    else: # For other tools like tavily_search
                        # ... (existing logic for other tools - seems okay)
                        if not isinstance(raw_result, str):
                            result_content_for_message = str(raw_result)
                        else:
                             result_content_for_message = raw_result
                        tool_messages_to_return.append(ToolMessage(tool_call_id=tool_call_id, name=tool_name, content=result_content_for_message))
                
                except Exception as e: # Error during tool_to_use.invoke()
                    print(f"Error invoking/processing tool {tool_name} with args {tool_args}: {e}")
                    traceback.print_exc()
                    result_content_for_message = f"Error executing tool {tool_name}: {e}"
                    tool_messages_to_return.append(ToolMessage(tool_call_id=tool_call_id, name=tool_name, content=result_content_for_message))
                    current_final_data = None 
                    current_final_tool_name = None
            else: # Tool name not found in self.tools
                 print(f"Warning: Tool '{tool_name}' not found in available tools {list(self.tools.keys())}.")
                 result_content_for_message = f"Error: Tool '{tool_name}' is not available."
                 tool_messages_to_return.append(ToolMessage(tool_call_id=tool_call_id, name=tool_name, content=result_content_for_message))

        print("--- Action Node Completed --- ")
        state_update = {'information': current_information} 
        if tool_messages_to_return:
            state_update['messages'] = tool_messages_to_return
        else:
             state_update['messages'] = [ToolMessage(tool_call_id="error", name="error", content="Internal error: Action node finished unexpectedly.")]

        state_update['final_response_data'] = current_final_data
        state_update['final_response_tool_name'] = current_final_tool_name
        
        if current_final_data is not None:
            print(f"Final response data IS SET. Tool: {current_final_tool_name}. Data type: {type(current_final_data)}")
        else:
            print("Final response data IS NOT SET.")
            
        return state_update

    def route_after_action(self, state: AgentState):
        """Checks if final_response_data is set and the source to decide the next step."""
        final_data = state.get("final_response_data")
        final_tool_name = state.get("final_response_tool_name")

        if final_data is not None:
            # If a flight was just selected, we want the LLM to formulate the final confirmation message.
            if final_tool_name == "confirmed_flight_selection":
                print("Routing after action: Flight selection confirmed. Continuing to LLM for final message formulation.")
                return "continue" # Go to call_llm_with_tools
            # For plan_da_nang_trip, the tool's output is now the final_data.
            # The LLM should formulate the response based on this rich data.
            elif final_tool_name == self.planner_tool.name: # plan_da_nang_trip
                print(f"Routing after action: '{self.planner_tool.name}' tool executed. Data prepared. Continuing to LLM for response formulation.")
                return "continue" # Go to call_llm_with_tools to formulate response from the rich plan object
            else:
                # For other tools that set final_data (like original tavily), finish directly.
                print(f"Routing after action: final_response_data found from tool '{final_tool_name}'. Finishing.")
                return "finish" # Routes to END
        else:
            # No final_response_data set by the action, so continue to LLM for next step or tool call.
            print("Routing after action: No final_response_data. Continuing to LLM.")
            return "continue" # Routes to call_llm_with_tools

    def mark_not_related_node(self, state: AgentState):
        """Sets the final message to 'Not Related'."""
        print("Query marked as not related to Da Nang travel.")
        return {"messages": [AIMessage(content="I apologize, but I specialize only in travel related to Da Nang, Vietnam, including planning trips there and checking flights from major Vietnamese cities. I cannot answer questions outside this scope.")]}

    def retrieve_stored_information(self, state: AgentState):
        """Retrieves previously stored information based on user query and state."""
        print("---RETRIEVING STORED INFORMATION---")
        messages = state['messages']
        last_human_message = messages[-1]
        if not isinstance(last_human_message, HumanMessage):
            return {"messages": [AIMessage(content="I need your request to retrieve information.")], "final_response_tool_name": "error_no_human_message"}

        user_query = last_human_message.content.lower()
        information = state.get('information', {})
        response_message = "I couldn't find the specific information you asked for in my current memory."
        retrieved_data_type = "retrieved_nothing" # Default

        # Check for requests about confirmed/booked flights
        if ("booked" in user_query or "confirmed" in user_query or "selected flight" in user_query) and information.get('confirmed_booking_details'):
            response_message = f"Okay, here is the confirmed flight detail I have for you."
            retrieved_data_type = "retrieved_flight_details"

        # Check for requests about previously shown available flights
        elif ("available flights" in user_query or "flights again" in user_query or "show flights" in user_query) and information.get('available_flights'):
            flights = information['available_flights']
            if flights:
                response_message = f"Okay, here are the {len(flights)} flight options I found previously."
                retrieved_data_type = "retrieved_available_flights"
            else:
                response_message = "I found no available flights previously."
                retrieved_data_type = "retrieved_no_available_flights"

        # Check for requests about the current plan
        elif ("plan" in user_query or "itinerary" in user_query) and information.get('current_trip_plan'):
            response_message = f"Okay, here is the current trip plan we discussed."
            retrieved_data_type = "retrieved_plan"

        # Fallback if specific data not found or query is generic retrieval
        elif retrieved_data_type == "retrieved_nothing":
             if information:
                 response_message = "I found some information stored for our conversation, but not the specific item you asked for. Here is what I have:"
                 retrieved_data_type = "retrieved_generic_info"
             else:
                 response_message = "I don't have any specific information stored for our current conversation yet."
                 # retrieved_data_type remains "retrieved_nothing"

        return {
            "messages": [AIMessage(content=response_message)],
            "final_response_tool_name": retrieved_data_type # Signal what was retrieved
            }

    def run_conversation(self, query: str, thread_id: str | None = None):
        messages = [HumanMessage(content=query)]
        thread = {"configurable": {"thread_id": thread_id}}

        print(f"\n--- Running conversation for thread {thread_id} ---")
        print(f"User Query: {query}")

        response_payload = {
            "response": {"message": "Error: Agent could not produce a final response."},
            "intent": "error",
            "thread_id": thread_id,
            "type": "Error"
        }

        try:
            current_state_from_memory = self.graph.get_state(config=thread)
            initial_persistent_information = {"available_flights": None, "current_trip_plan": None, "confirmed_booking_details": None, "flight_search_completed_awaiting_selection": False}
            if current_state_from_memory and current_state_from_memory.values:
                 retrieved_info = current_state_from_memory.values.get('information')
                 if retrieved_info and isinstance(retrieved_info, dict):
                     initial_persistent_information = retrieved_info # Load existing
                     print(f"Loaded existing information from memory for thread {thread_id}")
                 # else: print for debugging if needed
            # else: print for debugging if needed

            initial_state_values: AgentState = {
                "messages": messages,
                "relevance_decision": None,
                "query_type": None,
                "intent": None,
                "final_response_data": None,
                "final_response_tool_name": None,
                "information": initial_persistent_information,
                "pending_clarification": None
            }
            final_state = self.graph.invoke(initial_state_values, config=thread)

            final_ai_message_content = "Error: Could not determine agent's final message."
            if final_state and 'messages' in final_state and final_state['messages']:
                final_graph_message_obj = final_state['messages'][-1]
                if isinstance(final_graph_message_obj, AIMessage):
                    final_ai_message_content = final_graph_message_obj.content
                elif isinstance(final_graph_message_obj, ToolMessage):
                    final_ai_message_content = f"Tool execution resulted in: {final_graph_message_obj.content}"
                    logging.warning(f"Graph ended with ToolMessage for thread {thread_id}: {final_graph_message_obj.content}")
                else:
                    final_ai_message_content = f"Conversation ended unexpectedly. Last message type: {type(final_graph_message_obj).__name__}"
                    logging.error(f"Graph ended with unexpected message type for thread {thread_id}: {type(final_graph_message_obj).__name__}")
            else:
                logging.error(f"Graph execution for {thread_id} finished with empty or invalid final state messages.")

            response_data_for_payload = {"message": final_ai_message_content}
            determined_intent = "general_qa_agent" # Default

            # Extract results from the *current turn's* graph execution
            final_response_data_from_turn = final_state.get("final_response_data")
            final_tool_name_from_turn = final_state.get("final_response_tool_name")
            # Output of the intent_router node for *this turn*
            current_turn_graph_intent = final_state.get("intent")
            current_turn_query_type = final_state.get("query_type")
            current_turn_relevance = final_state.get("relevance_decision")

            # Extract potentially persistent information (might be from previous turns, updated by current)
            persistent_information = final_state.get("information", {})
            # available_flights_in_persistent_state = persistent_information.get('available_flights', []) # Example if needed elsewhere

            # --- 1. Determine the primary intent for THIS response payload --- #

            if current_turn_relevance == "end":
                determined_intent = "not_related"
                # Message is already from mark_not_related_node
            elif final_response_data_from_turn is not None:
                # A tool in the *current turn* produced a definitive final output.
                # Use the tool name to determine intent and add data.
                if final_tool_name_from_turn == "confirmed_flight_selection":
                    determined_intent = "flight_selection_confirmed"
                    response_data_for_payload["selected_flight_details"] = final_response_data_from_turn
                elif final_tool_name_from_turn == 'plan_da_nang_trip':
                    determined_intent = "plan_agent" # Or "plan_generated" / "plan_updated"
                    # final_response_data_from_turn already contains the rich plan object
                    # (base_plan, user_specified_stops, notes)
                    response_data_for_payload["plan_details"] = final_response_data_from_turn
                    
                    # Move the detailed LLM conversational summary into plan_details
                    # and set a concise main message.
                    if isinstance(response_data_for_payload["plan_details"], dict):
                        response_data_for_payload["plan_details"]["conversational_summary"] = final_ai_message_content # The LLM's summary
                    else: # Should not happen, plan_details should be a dict
                        response_data_for_payload["plan_details"] = {"raw_data": final_response_data_from_turn, "conversational_summary": final_ai_message_content}
                    
                    # Set a concise message for the main response field
                    response_data_for_payload["message"] = "I have prepared a travel plan for you. Please see the details."

                elif final_tool_name_from_turn == "flights_found_summary":
                    determined_intent = "flights_found_awaiting_selection"
                    # Message is summary string, flights were stored in information *this turn*
                    response_data_for_payload["flights"] = persistent_information.get('available_flights', []) # Use get for safety
                elif final_tool_name_from_turn in ["flights_not_found_summary", "flights_tool_error_or_message", "flights_tool_format_error", "flights_tool_processing_error"]:
                    determined_intent = "flight_search_direct_message"
                    # Message is in final_response_data_from_turn.
                elif final_tool_name_from_turn:
                    determined_intent = "tool_result"
                    response_data_for_payload[f"{final_tool_name_from_turn}_data"] = final_response_data_from_turn
                else:
                    determined_intent = "unknown_tool_result_with_data"
                    response_data_for_payload["data"] = final_response_data_from_turn
            else:
                # No direct tool output *this turn*. Determine intent based on graph flow.
                if current_turn_query_type in ["persona", "history"]:
                    determined_intent = "direct_answer"
                elif current_turn_graph_intent == "retrieve_information":
                    determined_intent = "retrieve_information"
                    # The retrieve_stored_information node set the final_tool_name_from_turn
                    # Use that name to decide which data to potentially attach from persistent state
                    if final_tool_name_from_turn == "retrieved_flight_details" and persistent_information.get('confirmed_booking_details'):
                        response_data_for_payload["confirmed_flight_details"] = persistent_information['confirmed_booking_details']
                    elif final_tool_name_from_turn == "retrieved_available_flights" and persistent_information.get('available_flights'):
                        response_data_for_payload["flights"] = persistent_information['available_flights']
                    elif final_tool_name_from_turn == "retrieved_plan" and persistent_information.get('current_trip_plan'):
                        response_data_for_payload["plan_details"] = persistent_information['current_trip_plan']
                        # Ensure the message reflects what plan_details contains (it could be the rich object)
                        if isinstance(persistent_information['current_trip_plan'], dict):
                            if 'base_plan' in persistent_information['current_trip_plan'] and persistent_information['current_trip_plan'].get('user_specified_stops'):
                                final_ai_message_content = "Okay, here is the current trip plan, including the base itinerary and your specified stops."
                            elif 'base_plan' in persistent_information['current_trip_plan']:
                                final_ai_message_content = "Okay, here is the current base trip plan we discussed."
                            else: # Should be the rich plan structure
                                final_ai_message_content = "Okay, here is the stored travel plan information."
                        # Update the message in the payload if it was changed
                        response_data_for_payload["message"] = final_ai_message_content
                    elif final_tool_name_from_turn == "retrieved_generic_info":
                        response_data_for_payload["stored_information"] = persistent_information
                    # If retrieved_nothing or retrieved_no_available_flights, add no extra data.
                elif current_turn_graph_intent == "clarification_request": # Check if clarification was generated
                     determined_intent = "clarification_request"
                     # (Clarification node handles message, no extra data needed here)
                elif current_turn_graph_intent: # Fallback to intent router output
                     determined_intent = current_turn_graph_intent
                # Default determined_intent remains general_qa_agent if none of the above match

            # --- 2. Conditionally add data for specific intents (if not added above) --- #
            # Example: If flight_agent intent, maybe add available flights from persistent state
            # if determined_intent == "flight_agent" and not response_data_for_payload.get("flights") and persistent_information.get('available_flights'):
            #     response_data_for_payload["flights"] = persistent_information['available_flights']

            # Final payload structure
            response_payload = {
                "response": response_data_for_payload,
                "intent": determined_intent,
                "thread_id": thread_id,
                "type": "AI" if determined_intent != "error" else "Error"
            }

            if response_payload["intent"] == "error" and response_payload["type"] == "AI":
                response_payload["type"] = "Error" # Ensure type is error if intent is error
            if "message" not in response_payload["response"] : # Should always be there from initial setup
                 response_payload["response"]["message"] = "An unspecified error occurred."
            if response_payload["intent"] == "error" and response_payload["response"]["message"] == "Error: Could not determine agent's final message.":
                 response_payload["response"]["message"] = "Agent encountered an issue processing the request."


        except Exception as e:
             print(f"Critical Error during graph execution for query '{query}' in thread {thread_id}: {e}")
             traceback.print_exc()
             response_payload = {
                 "response": {"message": f"Error during processing: {str(e)}"},
                 "intent": "error",
                 "thread_id": thread_id,
                 "type": "Error"
             }

        valid_intents = ["plan_agent", "flight_agent", "information_agent", "general_qa_agent",
                         "direct_answer", "not_related", "error", "tool_result",
                         "flight_selection_confirmed", "flights_found_awaiting_selection",
                         "clarification_request", "flight_search_direct_message",
                         "unknown_tool_result_with_data", "retrieve_information"] # Added retrieve_information
        if response_payload["intent"] not in valid_intents:
             print(f"Warning: Final intent '{response_payload['intent']}' is not in the expected list. Defaulting to 'general_qa_agent'.")
             response_payload["intent"] = "general_qa_agent" # Fallback

        print(f"--- Returning response payload for thread {thread_id}: Intent='{response_payload['intent']}', Type='{response_payload['type']}' ---")
        # print(f"DEBUG: Full response payload: {json.dumps(response_payload, indent=2)}") # Optional: for deep debugging
        return response_payload

# Removed async example usage comments
    
    
