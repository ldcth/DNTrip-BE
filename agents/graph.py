import os
import traceback
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_openai import ChatOpenAI
from langchain_core.messages import AnyMessage, SystemMessage, HumanMessage, ToolMessage, AIMessage
from langchain_community.tools.tavily_search import TavilySearchResults
from agents.state import AgentState
from agents.tools import plan_da_nang_trip_tool, book_flights_tool
import sqlite3
import json
import logging
from .history_manager import summarize_conversation_history, prune_conversation_history

load_dotenv()

sqlite_conn = sqlite3.connect("checkpoints.sqlite", check_same_thread=False)
memory = SqliteSaver(conn=sqlite_conn)

class Agent:
    def __init__(self):
        self.system =  """You are a smart research assistant specialized in Da Nang travel.
Use the search engine ('tavily_search_results_json') to look up specific, current information relevant to Da Nang travel (e.g., weather, specific opening hours, event details) ONLY IF the user asks for general information that isn't about flights or planning.
If the user asks for a travel plan and specifies a duration (e.g., 'plan a 3 days 2 nights trip', 'make a plan for 1 week'), use the 'plan_da_nang_trip' tool. Extract the travel duration accurately.
If the user asks about flights (e.g., 'show me flights from Hanoi', 'find flights to Da Nang on April 19th', 'book flight from SGN'), use the 'book_flights' tool. Extract the origin city and date accurately. You ONLY have flight data for Hanoi (HAN) and Ho Chi Minh City (SGN) departing on 2025-04-21 and 2025-04-20. Politely inform the user if they ask for other origins or dates using this tool.
Answer questions ONLY if they are related to travel in Da Nang, Vietnam, including flights *originating* from other Vietnamese cities TO Da Nang (if data exists).
If a query is relevant but doesn't require planning, flight booking, or external web search, answer directly from your knowledge.
If a query is irrelevant (not about Da Nang travel, flights to/from relevant locations, or planning), politely decline.

**IMPORTANT:** When presenting flight results from the 'book_flights' tool:
- List each flight option returned by the tool.
- For each flight, include ALL these details EXACTLY as provided by the tool: flight ID (e.g., Vietnam Airlines 148), departure time, arrival time, flight duration, price, departure airport, and arrival airport.
- Do NOT summarize, omit fields, or combine entries.
- If the tool returns an error message instead of flights, relay that error message to the user.
"""
        self.llm = ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0,
                api_key=os.getenv("OPENAI_API_KEY")
            )
        self.tavily_search = TavilySearchResults(max_results=2)
        self.planner_tool = plan_da_nang_trip_tool
        self.flight_tool = book_flights_tool

        self.model = self.llm.bind_tools([self.tavily_search, self.planner_tool, self.flight_tool])

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
            self.exists_action,
            {True: "action", False: END}
        )
        self.graph.add_edge("direct_llm_answer", END)
        self.graph.add_edge("mark_not_related", END)

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
        self.tools = {t.name: t for t in [self.tavily_search, self.planner_tool, self.flight_tool]}

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
        """Checks if the user query is related to Da Nang travel (including flights)."""
        user_message = state['messages'][-1]
        if not isinstance(user_message, HumanMessage):
             print("Warning: Expected last message to be HumanMessage for relevance check.")
             return {"relevance_decision": "end"}

        relevance_prompt = SystemMessage(content="""Is the following user query related to travel IN or TO Da Nang, Vietnam? This includes requests for travel plans within Da Nang, flight searches originating from major Vietnamese cities (like Hanoi, Ho Chi Minh City) potentially going to Da Nang, or general questions about Da Nang.
Respond only with the word 'continue' if it IS related.
Respond only with the word 'end' if it IS NOT related.""")

        try:
            response = self.router_llm.invoke([relevance_prompt, user_message])
            decision = response.content.strip().lower()
            print(f"Relevance check for query '{user_message.content[:50]}...': {decision}")
            if decision not in ["continue", "end"]:
                print(f"Warning: Relevance check returned unexpected value: {decision}. Defaulting to 'end'.")
                decision = "end"
        except Exception as e:
             print(f"Error during relevance check: {e}")
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
- 'flight_agent': User is asking about flights, potentially to or from Da Nang (e.g., 'flights from Hanoi?', 'show flights on April 19th', 'book a flight from Saigon?').
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

    def exists_action(self, state: AgentState):
        last_message = state['messages'][-1]
        has_tools = (
            isinstance(last_message, AIMessage) and
            hasattr(last_message, 'tool_calls') and
            isinstance(last_message.tool_calls, list) and
            len(last_message.tool_calls) > 0
        )
        print(f"Checking for actions in last message ({type(last_message)}): {has_tools}")
        if isinstance(last_message, AIMessage) and hasattr(last_message, 'invalid_tool_calls') and last_message.invalid_tool_calls:
             print(f"Warning: LLM produced invalid tool calls: {last_message.invalid_tool_calls}")

        return has_tools

    def take_action(self, state: AgentState):
        """Executes tools based on the LLM's request. 
        If it's a successful book_flights call resulting in a list of flights,
        it puts the parsed list into final_response_data and returns.
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
        tool_messages_to_return = [] # Renamed from results
        
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
                result_content_for_llm = "Error: Tool execution failed to produce content."
                try:
                    # --- Execute the tool --- 
                    if isinstance(tool_args, dict):
                        raw_result = tool_to_use.invoke(tool_args)
                    else:
                         print(f"Warning: Tool args for {tool_name} are not a dict: {tool_args}. Attempting to invoke anyway.")
                         raw_result = tool_to_use.invoke(tool_args)

                    # --- Decide how to handle the result --- 
                    if tool_name == 'book_flights':
                        try:
                            # Parse the JSON string result from the tool
                            parsed_data = json.loads(raw_result) 
                            
                            # --- Check the structure of the parsed data --- 
                            flight_list = None 
                            
                            # Case A: It's a dictionary containing a 'flights' list
                            if isinstance(parsed_data, dict) and 'flights' in parsed_data and isinstance(parsed_data['flights'], list):
                                flight_list = parsed_data['flights']
                                print(f"Found 'flights' key with a list of {len(flight_list)} items.")
                            
                            # Case B: It's directly a list (fallback, less likely based on logs)
                            elif isinstance(parsed_data, list):
                                flight_list = parsed_data
                                print("Parsed data is directly a list.")
                            
                            # --- Process based on extracted flight_list or original parsed_data --- 
                            
                            # If we extracted a valid flight list:
                            if flight_list is not None: 
                                if flight_list: # List is not empty
                                    logging.info(f"Storing raw flight list ({len(flight_list)} items) in final_response_data.")
                                    return {"final_response_data": flight_list} 
                                else: # List is empty
                                    result_content_for_llm = "No flights found matching your criteria."
                                    print("Flight tool returned empty list. Preparing message for LLM.")
                            
                            # If we didn't get a list, check for error/message dicts in the original parsed_data
                            elif isinstance(parsed_data, dict) and 'error' in parsed_data:
                                result_content_for_llm = f"Error from flight tool: {parsed_data['error']}"
                                print("Flight tool returned error dict. Preparing message for LLM.")
                            elif isinstance(parsed_data, dict) and 'message' in parsed_data:
                                 result_content_for_llm = parsed_data['message']
                                 print("Flight tool returned message dict. Preparing message for LLM.")
                            
                            # Handle other unexpected formats
                            else:
                                print(f"Warning: Unexpected data format from book_flights tool: {type(parsed_data)}. Content: {str(raw_result)[:200]}")
                                result_content_for_llm = f"Received unexpected data format from the flight tool."

                        # Handle JSON parsing errors
                        except json.JSONDecodeError:
                            print(f"Error: book_flights tool did not return valid JSON: {raw_result}")
                            result_content_for_llm = f"Error: Flight tool returned invalid data."
                        # Handle other processing errors
                        except Exception as format_err:
                             print(f"Error processing flight data: {format_err}")
                             result_content_for_llm = f"Error processing flight results: {format_err}"
                        
                        # If we reach here, it means we need to send a ToolMessage back to LLM
                        tool_messages_to_return.append(ToolMessage(tool_call_id=tool_call_id, name=tool_name, content=result_content_for_llm))

                    # For tools OTHER than book_flights
                    else: 
                        # Ensure result is a string for the ToolMessage
                        if not isinstance(raw_result, str):
                            print(f"Warning: Tool {tool_name} returned non-string result: {type(raw_result)}. Converting to string.")
                            result_content_for_llm = str(raw_result)
                        else:
                             result_content_for_llm = raw_result
                        
                        # Append ToolMessage for other tools
                        tool_messages_to_return.append(ToolMessage(tool_call_id=tool_call_id, name=tool_name, content=result_content_for_llm))

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

        # --- Return accumulated ToolMessages (if any) --- 
        # This part is reached only if final_response_data was NOT set and returned earlier
        print("--- Action Node Completed --- ")
        if tool_messages_to_return:
            print(f"Returning {len(tool_messages_to_return)} ToolMessage(s) to LLM for processing.")
            for msg in tool_messages_to_return:
                 print(f"  Tool: {msg.name}, Content: {msg.content[:200]}...")
            return {'messages': tool_messages_to_return} 
        else:
             # This case should not happen if logic above is correct 
             # (either final_response_data is returned, or a tool message is generated)
             print("CRITICAL WARNING: take_action finished without setting final_response_data or preparing ToolMessages.")
             return {"messages": [ToolMessage(tool_call_id="error", name="error", content="Internal error: Action node finished unexpectedly.")]}

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
            initial_state = {"messages": messages, "relevance_decision": None, "query_type": None, "intent": None, "final_response_data": None}
            final_state = self.graph.invoke(initial_state, config=thread)

            # Determine intent from final state if available (might be set even if final_response_data is used)
            if final_state:
                final_query_type = final_state.get("query_type")
                final_relevance = final_state.get("relevance_decision")
                final_intent_field = final_state.get("intent") # Get intent potentially set by intent_router
                final_response_data = final_state.get("final_response_data")

                # Prioritize direct answer path
                if final_query_type in ["persona", "history"]:
                    intent = "direct_answer"
                # Prioritize book_flights success
                elif final_response_data is not None:
                    intent = "flight_agent"
                # Prioritize not related
                elif final_relevance == "end":
                     intent = "not_related"
                # Use intent set by intent_router if valid
                elif final_intent_field in ["plan_agent", "flight_agent", "information_agent", "general_qa_agent"]:
                     intent = final_intent_field
                # Fallback based on final message content if intent is still unknown (e.g., error occurred)
                else:
                    # Keep the original fallback logic based on final message
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

            # --- Check for final_response_data first --- 
            if final_state and final_state.get("final_response_data") is not None:
                 response_content = final_state["final_response_data"]
                 print(f"Graph finished. Using final_response_data (Type: {type(response_content)}). Intent: {intent}")
                 # Ensure intent is correctly set for this case
                 if intent != "flight_agent":
                     logging.warning(f"final_response_data was set, but intent is '{intent}'. Forcing to 'flight_agent'.")
                     intent = "flight_agent"
            
            # --- Otherwise, process final message as before --- 
            elif final_state and 'messages' in final_state and final_state['messages']:
                 final_message = final_state['messages'][-1]
                 print(f"Graph finished. Processing final message (Type: {type(final_message)}). Intent: {intent}")

                 if isinstance(final_message, AIMessage):
                     if hasattr(final_message, 'tool_calls') and final_message.tool_calls:
                         print("Warning: Graph ended with an AIMessage containing tool calls. The conversation might be incomplete.")
                     response_content = final_message.content
                     print(f"Final Answer (AIMessage): {response_content}")
                     # If intent wasn't set earlier (e.g., direct AIMessage from relevance check 'end'), check message content
                     if intent == "error" and "I apologize, but I specialize only in travel related to Da Nang" in response_content:
                         intent = "not_related"
                     # Explicitly set intent if LLM answers directly without tool use after intent routing
                     elif intent in ["plan_agent", "flight_agent", "information_agent", "general_qa_agent"] and not hasattr(final_message, 'tool_calls'):
                         print(f"LLM answered directly after intent routing ({intent}). Setting final intent.")
                         pass # Intent should already be correctly set from routing
                     elif intent == "error": # Fallback if intent still unknown
                        intent = "general_qa_agent" 

                 elif isinstance(final_message, ToolMessage):
                      print(f"Warning: Graph ended with a ToolMessage: Name='{final_message.name}', Content='{final_message.content[:100]}...'")
                      response_content = f"Tool Execution Result: {final_message.content}" # Fallback
                      for msg in reversed(final_state['messages'][:-1]):
                          if isinstance(msg, AIMessage) and msg.content:
                              print(f"Returning content from previous AIMessage: {msg.content}")
                              response_content = msg.content + f"\n\n[Tool Execution Result: {final_message.content}]"
                              break
                      # Intent should have been set before the tool call, keep it.
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

        # Ensure intent is one of the expected values or a status
        valid_intents = ["plan_agent", "flight_agent", "information_agent", "general_qa_agent", "direct_answer", "not_related", "error"]
        if intent not in valid_intents:
             print(f"Warning: Final intent '{intent}' is not in the expected list. Setting to 'general_qa_agent'.")
             intent = "general_qa_agent" # Fallback to a sensible default if something unexpected happened

        print(f"--- Returning response with intent: {intent} ---")
        return {"response": response_content, "intent": intent}

# Example of how the agent might be used in app.py (conceptual)
# if __name__ == "__main__":
#     agent = Agent()
#     while True:
#         query = input("Ask about Da Nang travel: ")
#         if query.lower() in ["exit", "quit"]:
#             break
#         response = agent.run_conversation(query)
#         print("\nAgent Response:")
#         print(response)
#         print("-" * 30)
    
    
