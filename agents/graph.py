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
If the user asks for a travel plan and specifies a duration (e.g., 'plan a 3 days 2 nights trip', 'make a plan for 1 week'), use the 'plan_da_nang_trip' tool. Extract the travel duration accurately.

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
- 'missing_parameter_name': A string describing the specific piece of information that is missing (e.g., 'travel_duration', 'flight_origin_city', 'flight_date', 'flight_selection_details').
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
- 'history': Questions about the conversation history (e.g., 'What was my last question?')
- 'content': Any other type of question, including travel planning, flight searches, or general info requests.
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
        print(f"DEBUG: information at start of check_relevance: {json.dumps(information_at_relevance_check_start, indent=2)}")
        # Define how many recent messages to include as context (includes the current user message)
        HISTORY_CONTEXT_SIZE = 5 

        if not state['messages']:
            print("Error: No messages in state for relevance check.")
            return {"relevance_decision": "end"} # Should not happen in normal flow

        # Get the current user message (which is the last one in the list)
        current_user_message_for_logging = state['messages'][-1] # Renamed to avoid conflict
        if not isinstance(current_user_message_for_logging, HumanMessage):
            print("Warning: Expected last message to be HumanMessage for relevance check.")
            # Fallback behavior is implicitly handled by how history_selection_for_llm is processed,
            # ensuring if the last message is HumanMessage, it's likely included.

        # Take the last HISTORY_CONTEXT_SIZE messages.
        start_index = max(0, len(state['messages']) - HISTORY_CONTEXT_SIZE)
        history_selection_for_llm = state['messages'][start_index:]

        # Filter out any leading ToolMessages from history_selection_for_llm
        # as they cannot validly follow a SystemMessage in the final list for the LLM.
        first_valid_idx = 0
        if history_selection_for_llm: # Only iterate if not empty
            for idx, msg in enumerate(history_selection_for_llm):
                if not isinstance(msg, ToolMessage):
                    first_valid_idx = idx
                    break
                # If all messages in the slice are ToolMessages (idx reaches end and last msg is ToolMessage)
                if idx == len(history_selection_for_llm) - 1 and isinstance(msg, ToolMessage):
                    first_valid_idx = len(history_selection_for_llm) # This will make the slice empty
            
        processed_history_for_llm = history_selection_for_llm[first_valid_idx:]

        # If processed_history_for_llm became empty after filtering (e.g., the slice only contained ToolMessages),
        # and the actual last message in the full state is a HumanMessage (the user's current query),
        # ensure that this HumanMessage is included in the history for the relevance check LLM.
        if not processed_history_for_llm and isinstance(state['messages'][-1], HumanMessage):
            processed_history_for_llm = [state['messages'][-1]]


        relevance_prompt_system_message = SystemMessage(
            content="""Analyze the provided conversation history (if any) and the LATEST user query.
Your goal is to determine if the LATEST USER QUERY is a relevant continuation of the Da Nang travel-focused conversation, or if it's an unrelated topic.

Specifically, the LATEST USER QUERY IS RELEVANT (respond 'continue') if it:
1. Directly asks about travel IN or TO Da Nang, Vietnam (e.g., planning, flights, attractions, general info about Da Nang).
2. Is a direct response to a question the assistant just asked (e.g., assistant asks for date, user provides date).
3. Is an action or selection related to options the assistant just presented (e.g., assistant shows flights, user says 'book the first one'; assistant shows hotel options, user picks one).

The LATEST USER QUERY IS NOT RELEVANT (respond 'end') if it introduces a topic clearly outside of Da Nang travel and is not a direct follow-up to an assistant's question or presented options (e.g., 'who is the president?', 'what's the capital of France?') unless that question was explicitly solicited by the assistant for some reason.

Respond only with the single word 'continue' or 'end'."""
        )

        messages_for_llm = [relevance_prompt_system_message] + processed_history_for_llm

        # Log the types of messages being sent for relevance check
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
- 'plan_agent': User wants a travel plan/itinerary for Da Nang (e.g., 'plan a 3 day trip to Da Nang', 'make an itinerary').
- 'flight_agent': User is asking about flights, potentially to or from Da Nang (e.g., 'flights from Hanoi?', 'show flights on date', 'book a flight from Saigon?', 'select the first flight', 'the one at 9pm').
- 'information_agent': User is asking a question likely requiring external, up-to-date information about Da Nang (weather, opening hours, specific events, prices) that isn't about flights or planning.
- 'general_qa_agent': User is asking a general question about Da Nang that might be answerable from general knowledge or conversation history, without needing specific tools.
Respond only with 'plan_agent', 'flight_agent', 'information_agent', or 'general_qa_agent'."""
        intent_prompt = SystemMessage(content=intent_prompt_text)

        try:
            response = self.router_llm.invoke([intent_prompt, user_message])
            intent = response.content.strip().lower()
            print(f"LLM-based intent routing for query '{user_message.content[:50]}...': {intent}")
            valid_intents = ["plan_agent", "flight_agent", "information_agent", "general_qa_agent"]
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
        print(f"Routing based on intent: {intent}")
        if intent:
            if intent in ["plan_agent", "flight_agent", "information_agent", "general_qa_agent"]:
                return intent
            else:
                print(f"Warning: Invalid intent '{intent}' found in state. Defaulting to error.")
                return "error"
        else:
            print("Warning: Intent not found in state. Defaulting to error.")
            return "error"

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
                                current_information.pop('available_flights', None)
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
                        # ... (existing logic for planner_tool - seems okay)
                        try:
                            parsed_data = json.loads(raw_result)
                            if isinstance(parsed_data, dict) and parsed_data and not parsed_data.get('error'):
                                current_final_data = parsed_data 
                                current_final_tool_name = tool_name
                                result_content_for_message = "Successfully generated the travel plan."
                                current_information['current_trip_plan'] = parsed_data 
                            elif isinstance(parsed_data, dict) and ('error' in parsed_data or 'message' in parsed_data):
                                result_content_for_message = parsed_data.get('error') or parsed_data.get('message')
                                current_final_data = None 
                                current_final_tool_name = None
                            else:
                                result_content_for_message = raw_result 
                                current_final_data = None
                                current_final_tool_name = None
                        except json.JSONDecodeError:
                            result_content_for_message = raw_result 
                            current_final_data = None
                            current_final_tool_name = None
                        except Exception as format_err:
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
            else:
                # For other tools that set final_data (like planner), finish directly.
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
            current_turn_graph_intent = final_state.get("intent") # Output of intent_router for this turn
            current_turn_query_type = final_state.get("query_type") # Output of initial_router
            current_turn_relevance = final_state.get("relevance_decision") # Output of relevance_checker

            # Extract potentially persistent information (might be from previous turns, updated by current)
            persistent_information = final_state.get("information", {})
            available_flights_in_persistent_state = persistent_information.get('available_flights', [])
            # flight_search_completed_flag_in_state = persistent_information.get('flight_search_completed_awaiting_selection', False)

            # 1. Determine the primary intent for THIS response payload
            if current_turn_relevance == "end":
                determined_intent = "not_related"
                # Message is already from mark_not_related_node, no extra data needed.
            elif final_response_data_from_turn is not None:
                # A tool in the current turn produced a definitive final output that should be part of the payload
                if final_tool_name_from_turn == "confirmed_flight_selection":
                    determined_intent = "flight_selection_confirmed"
                    response_data_for_payload["selected_flight_details"] = final_response_data_from_turn
                elif final_tool_name_from_turn == 'plan_da_nang_trip':
                    determined_intent = "plan_agent" # Or "plan_generated"
                    response_data_for_payload["plan_details"] = final_response_data_from_turn
                elif final_tool_name_from_turn == "flights_found_summary":
                    determined_intent = "flights_found_awaiting_selection"
                    # Message in final_response_data_from_turn is the summary string from the tool.
                    # Flights data was stored in 'information' by take_action in *this turn*.
                    response_data_for_payload["flights"] = available_flights_in_persistent_state
                elif final_tool_name_from_turn in ["flights_not_found_summary", "flights_tool_error_or_message", "flights_tool_format_error", "flights_tool_processing_error"]:
                    determined_intent = "flight_search_direct_message" # Tool gave a message, no structured flight data.
                    # Message is in final_response_data_from_turn.
                elif final_tool_name_from_turn: # A generic tool result
                    determined_intent = "tool_result"
                    response_data_for_payload[f"{final_tool_name_from_turn}_data"] = final_response_data_from_turn
                else: # final_response_data_from_turn is not None, but final_tool_name_from_turn is None.
                      # This path should ideally not be hit if take_action always sets final_tool_name_from_turn when setting final_response_data_from_turn.
                    determined_intent = "unknown_tool_result_with_data"
                    response_data_for_payload["data"] = final_response_data_from_turn
            else:
                # final_response_data_from_turn is None. The graph ended with an AIMessage not directly from a tool's structured output.
                # This could be a direct LLM answer, a clarification, or an LLM-formulated response after a tool.
                if current_turn_query_type in ["persona", "history"]:
                    determined_intent = "direct_answer"
                elif current_turn_graph_intent: # Use intent from intent_router for current query
                    determined_intent = current_turn_graph_intent # e.g., "plan_agent", "flight_agent", "general_qa_agent"

                    # Check if this turn resulted in a clarification request being generated
                    messages_history = final_state.get('messages', [])
                    if len(messages_history) >= 3 and \
                       isinstance(messages_history[-1], AIMessage) and \
                       isinstance(messages_history[-2], ToolMessage) and \
                       isinstance(messages_history[-3], AIMessage) and \
                       hasattr(messages_history[-3], 'tool_calls') and messages_history[-3].tool_calls:
                        for tc in messages_history[-3].tool_calls:
                            if tc.get('name') == self.request_clarification_tool.name and \
                               tc.get('id') == messages_history[-2].tool_call_id:
                                determined_intent = "clarification_request"
                                break
                elif "I apologize, but I specialize only in travel related to Da Nang" in final_ai_message_content:
                    determined_intent = "not_related" # Fallback if relevance check somehow missed it

            # 2. Conditionally add structured data if current intent warrants it and data exists from a previous relevant turn
            #    (This is mainly for flight_agent when LLM answers from history without re-running the tool)
            if determined_intent == "flight_agent" and \
               final_response_data_from_turn is None and \
               determined_intent != "clarification_request" and \
               available_flights_in_persistent_state:
                # Current query is about flights (e.g. "show them again", "what about the vietjet one?"),
                # LLM is answering (no tool summary *this turn*), it's not a clarification, AND flights were previously found.
                response_data_for_payload["flights"] = available_flights_in_persistent_state
                # Consider if intent should be 'flights_found_awaiting_selection' here for consistency,
                # but 'flight_agent' with 'flights' data also works.

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
                         "unknown_tool_result_with_data"] # Added new potential intents
        if response_payload["intent"] not in valid_intents:
             print(f"Warning: Final intent '{response_payload['intent']}' is not in the expected list. Defaulting to 'general_qa_agent'.")
             response_payload["intent"] = "general_qa_agent" # Fallback

        print(f"--- Returning response payload for thread {thread_id}: Intent='{response_payload['intent']}', Type='{response_payload['type']}' ---")
        # print(f"DEBUG: Full response payload: {json.dumps(response_payload, indent=2)}") # Optional: for deep debugging
        return response_payload

# Removed async example usage comments
    
    
