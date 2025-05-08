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
from agents.tools import plan_da_nang_trip_tool, book_flights_tool, RequestClarificationArgs
import sqlite3 # Keep for potential future use or context
import json
import logging
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
If the user asks about flights (e.g., 'show me flights from Hanoi', 'find flights to Da Nang on date', 'book flight from SGN'), use the 'book_flights' tool. Extract the origin city and date accurately. You ONLY have flight data for Hanoi (HAN) and Ho Chi Minh City (SGN) departing on tomorrow and the day after tomorrow in the year 2025. Politely inform the user if they ask for other origins or dates using this tool.

When essential information for using a tool is missing (e.g., travel duration for 'plan_da_nang_trip', origin/destination or date for 'book_flights'),
DO NOT attempt to use the tool with incomplete information or guess the missing details.
Instead, you MUST call the 'request_clarification_tool'.
When calling 'request_clarification_tool', provide the following arguments:
- 'missing_parameter_name': A string describing the specific piece of information that is missing (e.g., 'travel_duration', 'flight_origin_city', 'flight_destination_city', 'flight_date').
- 'original_tool_name': The name of the tool you intended to use (e.g., 'plan_da_nang_trip', 'book_flights').

Answer questions ONLY if they are related to travel in Da Nang, Vietnam, including flights *originating* from other Vietnamese cities TO Da Nang (if data exists).
If a query is relevant but doesn't require planning, flight booking, or external web search, answer directly from your knowledge.
If a query is irrelevant (not about Da Nang travel, flights to/from relevant locations, or planning), politely decline.
"""
        self.llm = ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0,
                api_key=os.getenv("OPENAI_API_KEY")
            )
        self.tavily_search = TavilySearchResults(max_results=2)
        self.planner_tool = plan_da_nang_trip_tool
        self.flight_tool = book_flights_tool

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
            self.request_clarification_tool # Use the structured tool definition
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
        self.tools = {t.name: t for t in [self.tavily_search, self.planner_tool, self.flight_tool]}
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
        
        # Define how many recent messages to include as context (includes the current user message)
        HISTORY_CONTEXT_SIZE = 5 

        if not state['messages']:
            print("Error: No messages in state for relevance check.")
            return {"relevance_decision": "end"} # Should not happen in normal flow

        # Get the current user message (which is the last one in the list)
        current_user_message = state['messages'][-1]
        if not isinstance(current_user_message, HumanMessage):
            print("Warning: Expected last message to be HumanMessage for relevance check.")
            # Fallback: treat only the current message as the query if type is unexpected
            # This path should ideally not be taken.
            history_for_llm = [current_user_message]
        else:
            # Take the last HISTORY_CONTEXT_SIZE messages. This includes the current HumanMessage.
            start_index = max(0, len(state['messages']) - HISTORY_CONTEXT_SIZE)
            history_for_llm = state['messages'][start_index:]

        relevance_prompt_system_message = SystemMessage(
            content="""Analyze the provided conversation history (if any) and the LATEST user query.
Is the LATEST USER QUERY related to travel IN or TO Da Nang, Vietnam? 
This includes requests for travel plans within Da Nang, flight searches originating from major Vietnamese cities (like Hanoi, Ho Chi Minh City) potentially going to Da Nang, or general questions about Da Nang.
Consider if the latest user query is a direct response or follow-up to a previous question from the assistant. An otherwise ambiguous query might be relevant in the context of the conversation.
For example, if the assistant asked 'How long will your trip be?', a user response like 'for 3 days' IS relevant.
Respond only with the word 'continue' if the LATEST USER QUERY IS related in the context of the conversation.
Respond only with the word 'end' if the LATEST USER QUERY IS NOT related, even considering the history."""
        )

        messages_for_llm = [relevance_prompt_system_message] + history_for_llm

        # Log the types of messages being sent for relevance check
        print(f"Messages for relevance check LLM (types): {[msg.type for msg in messages_for_llm]}")
        # For more detailed debugging, uncomment to see content:
        # for i, msg in enumerate(messages_for_llm):
        #     content_preview = str(msg.content)[:100].replace("\n", " ") + "..." if len(str(msg.content)) > 100 else str(msg.content)
        #     print(f"  LLM msg {i} ({msg.type}): {content_preview}")

        try:
            response = self.router_llm.invoke(messages_for_llm)
            decision = response.content.strip().lower()
            # Use current_user_message for logging the query content itself
            print(f"Relevance check for query '{str(current_user_message.content)[:50]}...' (with history): {decision}")
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
        user_message = state['messages'][-1]
        if not isinstance(user_message, HumanMessage):
            print("Warning: Expected last message to be HumanMessage for intent routing.")
            return {"intent": "error"}

        intent_prompt = SystemMessage(content="""Given the user query (which is relevant to Da Nang travel), classify the primary intent:
- 'plan_agent': User wants a travel plan/itinerary for Da Nang (e.g., 'plan a 3 day trip to Da Nang', 'make an itinerary').
- 'flight_agent': User is asking about flights, potentially to or from Da Nang (e.g., 'flights from Hanoi?', 'show flights on date', 'book a flight from Saigon?').
- 'information_agent': User is asking a question likely requiring external, up-to-date information about Da Nang (weather, opening hours, specific events, prices) that isn't about flights or planning.
- 'general_qa_agent': User is asking a general question about Da Nang that might be answerable from general knowledge or conversation history, without needing specific tools.
Respond only with 'plan_agent', 'flight_agent', 'information_agent', or 'general_qa_agent'.""")

        try:
            response = self.router_llm.invoke([intent_prompt, user_message])
            intent = response.content.strip().lower()
            print(f"Intent routing for query '{user_message.content[:50]}...': {intent}")
            valid_intents = ["plan_agent", "flight_agent", "information_agent", "general_qa_agent"]
            if intent not in valid_intents:
                print(f"Warning: Intent routing returned unexpected value: {intent}. Defaulting to 'general_qa_agent'.")
                intent = "general_qa_agent"
        except Exception as e:
             print(f"Error during intent routing: {e}")
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
        messages = state['messages']

        # <<< APPLY HISTORY MANAGEMENT HERE >>>
        # Option 1: Summarization
        messages = summarize_conversation_history(messages, self.llm) # Pass the appropriate LLM instance
        # Option 2: Pruning
        # messages = prune_conversation_history(messages)

        if not any(isinstance(m, SystemMessage) for m in messages):
            messages = [SystemMessage(content=self.system)] + messages

        print("Messages being sent to LLM:")
        for msg in messages:
            print(f"  - Type: {type(msg).__name__}")
            if isinstance(msg, ToolMessage):
                 print(f"    Tool Call ID: {msg.tool_call_id}")
                 print(f"    Tool Name: {msg.name}")
                 print(f"    Tool Content (JSON String): {msg.content[:500]}...")
            else:
                 print(f"    Content: {str(msg.content)[:100]}...")

        print(f"Calling model with potentially modified messages: {[m.type for m in messages]}")
        message = self.model.invoke(messages)
        print(f"LLM response type: {message.type}")
        if hasattr(message, 'tool_calls') and message.tool_calls:
             print(f"LLM requested tool calls: {message.tool_calls}")
        else:
             print("LLM did not request tool calls.")

        return {'messages': [message]}

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
                Original Tool: 'book_flights'
                Missing Parameter: 'flight_origin_city'
                Natural Question: "I can help you with flights! What city will you be departing from?"
                
                Example 3:
                Original Tool: 'book_flights'
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
        If it's a successful book_flights or plan_da_nang_trip call
        resulting in parsable JSON data, it puts the parsed data into
        final_response_data and the tool name into final_response_tool_name.
        Otherwise, it prepares content for a ToolMessage and returns that.
        """
        last_message = state['messages'][-1]

        if not (isinstance(last_message, AIMessage) and
                hasattr(last_message, 'tool_calls') and
                isinstance(last_message.tool_calls, list) and
                len(last_message.tool_calls) > 0):
             print("Error: take_action called unexpectedly. Last message doesn't have valid tool calls.")
             # Return message to let graph continue and potentially report error
             return {'messages': [ToolMessage(tool_call_id="error", name="error", content="Internal error: Agent tried to take action without a valid tool call.")]}

        tool_calls = last_message.tool_calls
        tool_messages_to_return = []
        final_data_to_return = None
        final_tool_name_for_data = None # To store the name of the tool providing final data

        for t in tool_calls:
            tool_call_id = t.get('id')
            if not tool_call_id:
                print(f"Warning: Tool call missing 'id': {t}. Skipping.")
                continue

            tool_name = t.get('name')
            tool_args = t.get('args', {})

            print(f"Attempting to call tool: {tool_name} with args: {tool_args} (Call ID: {tool_call_id})")
            if tool_name in self.tools:
                tool_to_use = self.tools[tool_name]
                result_content_for_message = f"Error: Tool {tool_name} execution failed." # Default content

                try:
                    # --- Execute the tool ---
                    if isinstance(tool_args, dict):
                        raw_result = tool_to_use.invoke(tool_args)
                    else:
                         print(f"Warning: Tool args for {tool_name} are not a dict: {tool_args}. Attempting to invoke anyway.")
                         raw_result = tool_to_use.invoke(tool_args)

                    # --- Decide how to handle the result ---

                    # Handle book_flights
                    if tool_name == 'book_flights':
                        try:
                            parsed_data = json.loads(raw_result)
                            flight_list = None
                            if isinstance(parsed_data, dict) and 'flights' in parsed_data and isinstance(parsed_data['flights'], list):
                                flight_list = parsed_data['flights']
                                print(f"Found 'flights' key with a list of {len(flight_list)} items.")
                            elif isinstance(parsed_data, list):
                                flight_list = parsed_data
                                print("Parsed data is directly a list.")

                            if flight_list is not None:
                                if flight_list:
                                    logging.info(f"Storing raw flight list ({len(flight_list)} items) in final_response_data.")
                                    final_data_to_return = flight_list
                                    final_tool_name_for_data = tool_name # Store tool name
                                    result_content_for_message = f"Successfully retrieved {len(flight_list)} flights."
                                else:
                                    result_content_for_message = "No flights found matching your criteria."
                                    print("Flight tool returned empty list. Preparing message.")
                            elif isinstance(parsed_data, dict) and 'error' in parsed_data:
                                result_content_for_message = f"Error from flight tool: {parsed_data['error']}"
                                print("Flight tool returned error dict. Preparing message.")
                            elif isinstance(parsed_data, dict) and 'message' in parsed_data:
                                 result_content_for_message = parsed_data['message']
                                 print("Flight tool returned message dict. Preparing message.")
                            else:
                                result_content_for_message = f"Received unexpected data format from the flight tool."
                        except json.JSONDecodeError:
                            print(f"Error: book_flights tool did not return valid JSON: {raw_result}")
                            result_content_for_message = f"Error: Flight tool returned invalid data."
                        except Exception as format_err:
                             print(f"Error processing flight data: {format_err}")
                             result_content_for_message = f"Error processing flight results: {format_err}"

                        # Append the ToolMessage for book_flights
                        tool_messages_to_return.append(ToolMessage(tool_call_id=tool_call_id, name=tool_name, content=result_content_for_message))

                    # Handle plan_da_nang_trip
                    elif tool_name == 'plan_da_nang_trip':
                        try:
                            # Attempt to parse the result as JSON (assuming the tool returns a JSON string representing the plan dict)
                            parsed_data = json.loads(raw_result)

                            # Basic check: Ensure it's a dictionary (or could be list if tool changes)
                            if isinstance(parsed_data, dict) and parsed_data: # Check if it's a non-empty dict
                                logging.info(f"Storing parsed plan data in final_response_data.")
                                final_data_to_return = parsed_data
                                final_tool_name_for_data = tool_name # Store tool name
                                result_content_for_message = "Successfully generated the travel plan."
                            elif isinstance(parsed_data, dict) and 'error' in parsed_data: # Check for potential error structure
                                result_content_for_message = f"Error from planning tool: {parsed_data['error']}"
                                print("Planning tool returned error dict. Preparing message.")
                            elif isinstance(parsed_data, dict) and 'message' in parsed_data: # Check for potential message structure
                                result_content_for_message = parsed_data['message']
                                print("Planning tool returned message dict. Preparing message.")
                            else:
                                # If it parsed but wasn't a recognized successful structure
                                print(f"Warning: plan_da_nang_trip tool returned unexpected JSON structure: {type(parsed_data)}. Treating as simple content.")
                                result_content_for_message = raw_result # Fallback to raw string for ToolMessage

                        except json.JSONDecodeError:
                            # If it's not JSON, treat the raw result as the content for the next LLM call
                            print(f"Info: plan_da_nang_trip tool did not return valid JSON. Treating as text content: {raw_result[:100]}...")
                            result_content_for_message = raw_result
                        except Exception as format_err:
                             print(f"Error processing plan data: {format_err}")
                             result_content_for_message = f"Error processing plan results: {format_err}"

                        # Append the ToolMessage for plan_da_nang_trip
                        tool_messages_to_return.append(ToolMessage(tool_call_id=tool_call_id, name=tool_name, content=result_content_for_message))

                    # Handle other tools (e.g., tavily_search)
                    else:
                        # Ensure result is a string for the ToolMessage
                        if not isinstance(raw_result, str):
                            print(f"Warning: Tool {tool_name} returned non-string result: {type(raw_result)}. Converting to string.")
                            result_content_for_message = str(raw_result)
                        else:
                             result_content_for_message = raw_result

                        # Append ToolMessage for other tools
                        tool_messages_to_return.append(ToolMessage(tool_call_id=tool_call_id, name=tool_name, content=result_content_for_message))

                # Handle errors during tool invocation itself
                except Exception as e:
                    print(f"Error invoking/processing tool {tool_name} with args {tool_args}: {e}")
                    traceback.print_exc()
                    # Append error message for LLM
                    tool_messages_to_return.append(ToolMessage(tool_call_id=tool_call_id, name=tool_name, content=f"Error executing tool {tool_name}: {e}"))

            # Handle case where tool name is not found
            else:
                 print(f"Warning: Tool '{tool_name}' not found in available tools {list(self.tools.keys())}.")
                 # Append error message for LLM
                 tool_messages_to_return.append(ToolMessage(tool_call_id=tool_call_id, name=tool_name, content=f"Error: Tool '{tool_name}' is not available."))

        # --- Return accumulated ToolMessages AND potential final data ---
        print("--- Action Node Completed --- ")
        state_update = {}
        if tool_messages_to_return:
            print(f"Adding {len(tool_messages_to_return)} ToolMessage(s) to state for history.")
            state_update['messages'] = tool_messages_to_return
        else:
             # Should not happen if logic is correct
             print("CRITICAL WARNING: take_action finished without preparing ToolMessages.")
             state_update['messages'] = [ToolMessage(tool_call_id="error", name="error", content="Internal error: Action node finished unexpectedly.")]

        if final_data_to_return is not None:
            print("Adding final_response_data and final_response_tool_name to state.")
            print(f"Value of final_tool_name_for_data right before adding to state_update: {final_tool_name_for_data}")
            state_update['final_response_data'] = final_data_to_return
            state_update['final_response_tool_name'] = final_tool_name_for_data # Add tool name here

        return state_update # Return dict containing messages and potentially final_response_data/tool_name

    def route_after_action(self, state: AgentState):
        """Checks if final_response_data is set to decide the next step."""
        if state.get("final_response_data") is not None:
            print("Routing after action: final_response_data found. Finishing.")
            return "finish"
        else:
            print("Routing after action: No final_response_data. Continuing to LLM.")
            return "continue"

    def mark_not_related_node(self, state: AgentState):
        """Sets the final message to 'Not Related'."""
        print("Query marked as not related to Da Nang travel.")
        return {"messages": [AIMessage(content="I apologize, but I specialize only in travel related to Da Nang, Vietnam, including planning trips there and checking flights from major Vietnamese cities. I cannot answer questions outside this scope.")]}

    def run_conversation(self, query: str, thread_id: str | None = None):
        messages = [HumanMessage(content=query)]
        thread = {"configurable": {"thread_id": thread_id}}

        print(f"\n--- Running conversation for thread {thread_id} ---")
        print(f"User Query: {query}")

        response_content = "Error: Agent could not produce a final response."
        intent = "error" # Default intent

        try:
            initial_state: AgentState = {
                "messages": messages,
                "relevance_decision": None,
                "query_type": None,
                "intent": None,
                "final_response_data": None,
                "final_response_tool_name": None,
                "information": None, 
                "pending_clarification": None 
            }
            final_state = self.graph.invoke(initial_state, config=thread) # Synchronous invoke

            # Determine intent from final state if available
            if final_state:
                final_query_type = final_state.get("query_type")
                final_relevance = final_state.get("relevance_decision")
                final_intent_field = final_state.get("intent") # Get intent potentially set by intent_router
                final_response_data = final_state.get("final_response_data")
                final_tool_name = final_state.get("final_response_tool_name") # <<< Get tool name <<<

                # --- Determine Intent ---
                # Priority 1: Final data exists - determine intent from tool name
                if final_response_data is not None:
                    if final_tool_name == 'book_flights':
                        intent = "flight_agent"
                    elif final_tool_name == 'plan_da_nang_trip':
                        intent = "plan_agent"
                    else:
                        # Should not happen if logic in take_action is correct
                        logging.warning(f"final_response_data exists but final_response_tool_name is '{final_tool_name}'. Falling back.")
                        intent = "general_qa_agent" # Or maybe error?
                # Priority 2: Direct Answer Path
                elif final_query_type in ["persona", "history"]:
                    intent = "direct_answer"
                # Priority 3: Not Related
                elif final_relevance == "end":
                     intent = "not_related"
                # Priority 4: Use intent set by intent_router if valid
                elif final_intent_field in ["plan_agent", "flight_agent", "information_agent", "general_qa_agent"]:
                     intent = final_intent_field
                # Priority 5: Fallback based on final message content
                else:
                    if final_state and 'messages' in final_state and final_state['messages']:
                        final_message = final_state['messages'][-1]
                        if isinstance(final_message, AIMessage):
                             if "I apologize, but I specialize only in travel related to Da Nang" in final_message.content:
                                 intent = "not_related"
                             else:
                                 intent = "general_qa_agent" # Default for other AIMessages
                        # ... (keep other message type fallbacks if needed) ...
                    else:
                         intent = "error" # If state is invalid

            # --- Get Response Content ---
            # Check for final_response_data first
            if final_state and final_response_data is not None:
                 response_content = final_response_data
                 print(f"Graph finished. Using final_response_data (Type: {type(response_content)}). Intent: {intent}")
            # Otherwise, process final message as before
            elif final_state and 'messages' in final_state and final_state['messages']:
                 final_message = final_state['messages'][-1]
                 print(f"Graph finished. Processing final message (Type: {type(final_message)}). Intent: {intent}")

                 if isinstance(final_message, AIMessage):
                     # Check if the graph ended correctly (no pending tool calls)
                     if hasattr(final_message, 'tool_calls') and final_message.tool_calls:
                         print("Warning: Graph ended with an AIMessage containing tool calls. The conversation might be incomplete.")
                     response_content = final_message.content
                     print(f"Final Answer (AIMessage): {response_content}")
                     # If intent wasn't set by prior logic (e.g. direct AIMessage from relevance check 'end'), check message content
                     if intent == "error" and "I apologize, but I specialize only in travel related to Da Nang" in response_content:
                         intent = "not_related"
                     # If intent is still error after an AIMessage, default to general_qa
                     elif intent == "error":
                         intent = "general_qa_agent"

                 elif isinstance(final_message, ToolMessage):
                      print(f"Warning: Graph ended with a ToolMessage: Name='{final_message.name}', Content='{final_message.content[:100]}...'")
                      response_content = f"Tool Execution Result: {final_message.content}" # Fallback
                      # Try to find the previous AI message for better context
                      for msg in reversed(final_state['messages'][:-1]):
                          if isinstance(msg, AIMessage) and msg.content:
                              print(f"Returning content from previous AIMessage: {msg.content}")
                              response_content = msg.content + f"\n\n[Tool Execution Result: {final_message.content}]"
                              break
                      # If intent wasn't set before the tool call somehow, mark it
                      if intent == "error": intent = "tool_result" # Set specific intent if unknown

                 elif isinstance(final_message, HumanMessage):
                     print("Warning: Graph ended with a HumanMessage. This is unexpected.")
                     response_content = "Error: Conversation ended unexpectedly after user input."
                     intent = "error"
                 else:
                     print(f"Warning: Unexpected final message type: {type(final_message)}")
                     response_content = f"Final State Info: {str(final_message)}"
                     intent = "error"
            else:
                 print("Error: Graph execution finished with an empty or invalid final state.")
                 intent = "error"

        except Exception as e:
             print(f"Critical Error during graph execution for query '{query}': {e}")
             traceback.print_exc()
             response_content = f"Error during processing: {e}"
             intent = "error" # Ensure intent is 'error' on exception

        # --- Final Intent Validation ---
        valid_intents = ["plan_agent", "flight_agent", "information_agent", "general_qa_agent", "direct_answer", "not_related", "error", "tool_result"]
        if intent not in valid_intents:
             print(f"Warning: Final intent '{intent}' is not in the expected list. Setting to 'general_qa_agent'.")
             intent = "general_qa_agent" # Fallback

        print(f"--- Returning response with intent: {intent} ---")
        # Return thread_id along with response for subsequent requests
        return {"response": response_content, "intent": intent, "thread_id": thread_id}

# Removed async example usage comments
    
    
