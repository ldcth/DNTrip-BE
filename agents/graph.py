import os
import traceback
from dotenv import load_dotenv
from langsmith import traceable
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.mongodb import MongoDBSaver
from pymongo import MongoClient
from langchain_openai import ChatOpenAI
from langchain_core.messages import AnyMessage, SystemMessage, HumanMessage, ToolMessage, AIMessage
from langchain_community.tools.tavily_search import TavilySearchResults
from agents.state import AgentState
from agents.tools import plan_da_nang_trip_tool, show_flights_tool, RequestClarificationArgs, select_flight_tool_func, SelectFlightArgs, search_places_rag_tool
from agents.progress_manager import progress_manager
import json
import logging
from services.flight_selection import select_flight_for_booking
from .history_manager import summarize_conversation_history, prune_conversation_history
from langchain.tools import StructuredTool
from .prompts import (
    SYSTEM_PROMPT,
    INITIAL_ROUTER_PROMPT,
    RELEVANCE_CHECK_PROMPT,
    INTENT_ROUTER_PROMPT,
    NATURAL_CLARIFICATION_PROMPT,
    DIRECT_ANSWER_SYSTEM_PROMPT,
    PLAN_AGENT_SYSTEM_PROMPT,
    FLIGHT_AGENT_SYSTEM_PROMPT,
    INFORMATION_AGENT_SYSTEM_PROMPT,
    PLACES_AGENT_SYSTEM_PROMPT,
    GENERAL_QA_SYSTEM_PROMPT,
)
from .agent_helpers import get_natural_clarification_question, prepare_response_payload

load_dotenv()

os.environ["LANGCHAIN_TRACING_V2"] = os.getenv("LANGCHAIN_TRACING_V2")
os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGCHAIN_API_KEY")
os.environ["LANGCHAIN_PROJECT"] = os.getenv("LANGCHAIN_PROJECT")


# mongodb_uri = os.getenv("MONGODB_URI")
# if not mongodb_uri:
#     raise ValueError("MONGODB_URI environment variable not set.")
# mongo_client = MongoClient(mongodb_uri)
# memory = MongoDBSaver(
#     client=mongo_client,
#     db_name="dntrip",
#     collection_name="langgraph_checkpoints"
# )

# Dummy function for the conceptual tool's schema
def _dummy_request_clarification_func(missing_parameter_name: str, original_tool_name: str):
    """This is a dummy function for schema purposes and should not be called directly."""
    print("WARNING: _dummy_request_clarification_func was called. This should not happen.")
    return "Error: Clarification dummy function was called."

class Agent:
    def __init__(self):
        self.llm = ChatOpenAI(
                model=os.getenv("MODEL_VERSION"),
                temperature=0,
                api_key=os.getenv("OPENAI_API_KEY")
            )
        self.tavily_search = TavilySearchResults(max_results=2)
        self.planner_tool = plan_da_nang_trip_tool
        self.flight_tool = show_flights_tool
        self.select_flight_tool = select_flight_tool_func
        self.rag_tool = search_places_rag_tool

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
            self.rag_tool,
            self.request_clarification_tool
        ])

        self.router_llm = ChatOpenAI(
                model=os.getenv("MODEL_VERSION"),
                temperature=0,
                api_key=os.getenv("OPENAI_API_KEY")
            )

        mongodb_uri = os.getenv("MONGODB_URI")
        if not mongodb_uri:
            raise ValueError("MONGODB_URI environment variable not set.")
        mongo_client = MongoClient(mongodb_uri)
        memory = MongoDBSaver(
            client=mongo_client,
            db_name="dntrip",
            collection_name="langgraph_checkpoints"
        )
        self.memory = memory

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
                "places_agent": "call_llm_with_tools",
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

        self.graph = self.graph.compile(checkpointer=self.memory)
        self.tools = {t.name: t for t in [self.tavily_search, self.planner_tool, self.flight_tool, self.select_flight_tool, self.rag_tool]}
        self.tools[self.request_clarification_tool.name] = None
        
        # For tracking current thread_id during conversation
        self._current_thread_id = None

    def _emit_progress(self, phase: str, message: str, tool_name: str = None, is_loading: bool = True):
        """Emit progress event for the current conversation thread"""
        if self._current_thread_id:
            progress_manager.emit_progress(
                thread_id=self._current_thread_id,
                phase=phase,
                message=message,
                tool_name=tool_name,
                is_loading=is_loading
            )

    def _get_system_prompt_for_intent(self, intent: str) -> str:
        """Get the appropriate system prompt based on the current intent."""
        prompt_mapping = {
            "plan_agent": PLAN_AGENT_SYSTEM_PROMPT,
            "flight_agent": FLIGHT_AGENT_SYSTEM_PROMPT,
            "information_agent": INFORMATION_AGENT_SYSTEM_PROMPT,
            "places_agent": PLACES_AGENT_SYSTEM_PROMPT,
            "general_qa_agent": GENERAL_QA_SYSTEM_PROMPT,
        }
        return prompt_mapping.get(intent, SYSTEM_PROMPT)  # Default to original prompt if intent not found

    def _get_tools_for_intent(self, intent: str) -> list:
        """Get the appropriate tools based on the current intent."""
        if intent == "plan_agent":
            return [self.planner_tool, self.request_clarification_tool]
        elif intent == "flight_agent":
            return [self.flight_tool, self.select_flight_tool, self.request_clarification_tool]
        elif intent == "places_agent":
            return [self.rag_tool, self.request_clarification_tool]
        elif intent == "information_agent":
            return [self.tavily_search, self.request_clarification_tool]
        elif intent == "general_qa_agent":
            return [self.request_clarification_tool]  # Minimal tools for general QA
        else:
            # Default: all tools available
            return [self.tavily_search, self.planner_tool, self.flight_tool, self.select_flight_tool, self.rag_tool, self.request_clarification_tool]

    def _prepare_messages_for_llm(self, current_messages: list[AnyMessage], system_prompt: str, max_human_interactions: int = 5) -> list[AnyMessage]:
        """
        Prepares a list of messages for the LLM by selecting a recent history slice
        and ensuring a system message is prepended.
        Filters out ToolMessages as they should be responses to tool_calls, not direct inputs without prior AIMessage.
        """
        system_message_to_use = SystemMessage(content=system_prompt)
        history_slice = []
        human_interaction_counter = 0

        # Iterate in reverse to get the most recent messages
        for message in reversed(current_messages):
            if isinstance(message, SystemMessage): # Skip any existing system messages in history
                continue
            # if isinstance(message, ToolMessage): # Skip ToolMessages entirely for direct LLM calls
            #     continue

            history_slice.insert(0, message) # Add to the beginning to maintain order

            if isinstance(message, HumanMessage):
                human_interaction_counter += 1
                if human_interaction_counter >= max_human_interactions:
                    break
      
        #  at least add the last human message if available, or a default one.
        # if not any(isinstance(msg, (HumanMessage, AIMessage)) for msg in history_slice):
        #     last_human_message_content = "Hello." # Default content
        #     for msg in reversed(current_messages): # Find the actual last human message
        #         if isinstance(msg, HumanMessage):
        #             last_human_message_content = msg.content
        #             break
        #     history_slice = [HumanMessage(content=last_human_message_content)]


        return [system_message_to_use] + history_slice

    def initial_router(self, state: AgentState):
        self._emit_progress("initial_router", "🔍 Understanding your request...")
        
        user_message = state['messages'][-1]
        if not isinstance(user_message, HumanMessage):
             print("Warning: Expected last message to be HumanMessage for initial routing.")
             return {"query_type": "content", "relevance_decision": None, "intent": None}

        routing_prompt = SystemMessage(content=INITIAL_ROUTER_PROMPT)

        try:
            response = self.router_llm.invoke([routing_prompt, user_message])
            query_type = response.content.strip().lower().strip('\'"')
            print(f"Initial routing for query '{user_message.content[:50]}...': {query_type}")
        except Exception as e:
             print(f"Error during initial routing: {e}")
             traceback.print_exc()
             query_type = "content"

        return {"query_type": query_type, "relevance_decision": None, "intent": None}

    def route_based_on_query_type(self, state: AgentState):
        query_type = state.get("query_type")
        validated_query_type = "content"
        if query_type:
             if query_type in ["persona", "history", "content"]:
                 validated_query_type = query_type
             else:
                 print(f"Warning: Unexpected query_type '{query_type}' found in route_based_on_query_type. Defaulting to 'content'.")
        else:
             print("Warning: Query type not found in state. Defaulting to 'content'.")
        
        print(f"--- route_based_on_query_type --- Returning decision: {validated_query_type}")
        return validated_query_type

    def direct_llm_answer(self, state: AgentState):
        self._emit_progress("direct_llm_answer", "💬 Preparing response...")
        
        messages_from_state = state['messages']
        
        # Use the specific prompt for direct answers (persona, history, simple questions)
        final_messages_for_llm = self._prepare_messages_for_llm(
            current_messages=messages_from_state,
            system_prompt=DIRECT_ANSWER_SYSTEM_PROMPT,
            max_human_interactions=5
        )
        
        # Use LLM without tools for direct answers
        # print(f"DEBUG: Messages being sent to self.llm.invoke in direct_llm_answer: {final_messages_for_llm}")
        response_message = self.llm.invoke(final_messages_for_llm)
        return {'messages': [response_message]}

    def check_relevance(self, state: AgentState):
        self._emit_progress("relevance_checker", "✅ Validating travel query...")
        
        print("--- Checking Relevance (with limited history & info) ---")

        if not state['messages'] or not isinstance(state['messages'][-1], HumanMessage):
            print("Error: No HumanMessage at the end of state for relevance check.")
            return {"relevance_decision": "end"}

        information_at_relevance_check_start = state.get("information", {})
        info_status = {}
        for k, v in information_at_relevance_check_start.items():
            if isinstance(v, (list, dict)):
                info_status[k] = f"len={len(v)}" if v else "empty"
            elif v is not None and v != False:
                info_status[k] = "present"
            else:
                info_status[k] = "empty/None"
        print(f"DEBUG: information status at start of check_relevance: {info_status}")

        HISTORY_CONTEXT_SIZE = 5

        current_user_message_for_logging = state['messages'][-1]
        start_index = max(0, len(state['messages']) - HISTORY_CONTEXT_SIZE)
        history_selection_for_llm = state['messages'][start_index:]

        first_valid_idx = 0
        if history_selection_for_llm:
            for idx, msg in enumerate(history_selection_for_llm):
                if not isinstance(msg, ToolMessage):
                    first_valid_idx = idx
                    break
            if first_valid_idx == len(history_selection_for_llm) -1 and isinstance(history_selection_for_llm[first_valid_idx], ToolMessage):
                 pass
            
            processed_history_for_llm = history_selection_for_llm[first_valid_idx:]
        else:
            processed_history_for_llm = [current_user_message_for_logging]

        if not processed_history_for_llm and isinstance(current_user_message_for_logging, HumanMessage):
            processed_history_for_llm = [current_user_message_for_logging]

        relevance_prompt_system_message = SystemMessage(
            content=RELEVANCE_CHECK_PROMPT.format(info_status=info_status) # Apply formatting here
        )

        messages_for_llm = [relevance_prompt_system_message] + processed_history_for_llm
        
        print(f"Messages for relevance check LLM (types): {[msg.type for msg in messages_for_llm]}")
        print(f"Latest user query for relevance: '{current_user_message_for_logging.content[:100]}...'")

        try:
            response = self.router_llm.invoke(messages_for_llm)
            decision = response.content.strip().lower()
            print(f"Relevance check for query '{str(current_user_message_for_logging.content)[:50]}...': {decision}")
            if decision not in ["continue", "end"]:
                print(f"Warning: Relevance check returned unexpected value: {decision}. Defaulting to 'end'.")
                decision = "end"
        except Exception as e:
            print(f"Error during relevance check (with history & info): {e}")
            traceback.print_exc()
            decision = "end"

        return {"relevance_decision": decision}

    def _fallback_relevance_check(self, user_message: HumanMessage, information: dict, conversation_history: list) -> str:
        """
        Fallback method to determine relevance when LLM doesn't follow strict instructions.
        Uses rule-based logic to analyze the query and context.
        """
        query = user_message.content.lower().strip()
        
        # Direct Da Nang travel keywords
        danang_keywords = [
            "da nang", "danang", "đà nẵng", "flight", "flights", "plan", "trip", "travel", 
            "hotel", "restaurant", "beach", "attraction", "ba na hills", "marble mountains", 
            "dragon bridge", "han market", "my khe", "hoi an", "hanoi", "ho chi minh", "saigon"
        ]
        
        # Flight-related actions that are clearly travel-related
        flight_actions = [
            "book", "select", "choose", "first", "second", "third", "flight", "1st", "2nd", "3rd"
        ]
        
        # Check for direct keyword matches
        if any(keyword in query for keyword in danang_keywords):
            print(f"Fallback: Found Da Nang keyword in query: {query}")
            return "continue"
        
        # Check for flight selection context
        if information.get('available_flights') and any(action in query for action in flight_actions):
            print(f"Fallback: Flight selection context detected with available flights")
            return "continue"
        
        # Check for plan modification context
        if information.get('current_trip_plan') and any(word in query for word in ["modify", "change", "add", "update", "plan"]):
            print(f"Fallback: Plan modification context detected")
            return "continue"
        
        # Check conversation history for flight/travel context
        if conversation_history:
            recent_context = " ".join([
                msg.content.lower() if hasattr(msg, 'content') and isinstance(msg.content, str) else ""
                for msg in conversation_history[-3:]  # Check last 3 messages
                if hasattr(msg, 'content')
            ])
            
            if any(keyword in recent_context for keyword in danang_keywords):
                print(f"Fallback: Found travel context in recent conversation history")
                return "continue"
        
        # If no clear relevance indicators found
        print(f"Fallback: No clear Da Nang travel relevance found in query or context")
        return "end"

    def route_based_on_relevance(self, state: AgentState):
        decision = state.get("relevance_decision")
        if decision:
             print(f"Routing based on relevance decision: {decision}")
             return decision
        else:
             print("Warning: Relevance decision not found in state. Defaulting to 'end'.")
             return "end"

    def route_intent(self, state: AgentState):
        self._emit_progress("intent_router", "🎯 Determining best approach...")
        
        print("--- Routing Intent ---")
        
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
                    if tc.get('id') == tool_ack_message.tool_call_id and \
                       tc.get('name') == self.request_clarification_tool.name:
                        
                        original_tool_name = tc.get('args', {}).get('original_tool_name')
                        if original_tool_name == 'show_flights':
                            print(f"Intent determined as follow-up to 'show_flights' clarification. Routing to flight_agent.")
                            return {"intent": "flight_agent"}
                        elif original_tool_name == 'plan_da_nang_trip':
                            print(f"Intent determined as follow-up to 'plan_da_nang_trip' clarification. Routing to plan_agent.")
                            return {"intent": "plan_agent"}
                        elif original_tool_name == 'select_flight_tool':
                            print(f"Intent determined as follow-up to 'select_flight_tool' clarification. Routing to flight_agent.")
                            return {"intent": "flight_agent"}
                        break

        user_message = state['messages'][-1]
        if not isinstance(user_message, HumanMessage):
            print("Warning: Expected last message to be HumanMessage for LLM-based intent routing.")
            return {"intent": "error"}

        intent_prompt = SystemMessage(content=INTENT_ROUTER_PROMPT)

        try:
            response = self.router_llm.invoke([intent_prompt, user_message])
            intent = response.content.strip().lower()
            print(f"LLM-based intent routing for query '{user_message.content[:50]}...': {intent}")
            valid_intents = ["plan_agent", "flight_agent", "information_agent", "retrieve_information", "places_agent", "general_qa_agent"]
            if intent not in valid_intents:
                print(f"Warning: LLM-based intent routing returned unexpected value: {intent}. Defaulting to 'general_qa_agent'.")
                intent = "general_qa_agent"
        except Exception as e:
             print(f"Error during LLM-based intent routing: {e}")
             traceback.print_exc()
             intent = "error"

        return {"intent": intent}

    def route_based_on_intent(self, state: AgentState):
        intent = state.get("intent")
        valid_intents = {'plan_agent', 'flight_agent', 'information_agent', 'retrieve_information', 'places_agent', 'general_qa_agent'}
        if intent not in valid_intents:
            print(f"Warning: Unrecognized intent '{intent}'. Routing to general QA.")
            return "general_qa_agent"
        print(f"Routing based on intent: {intent}")
        return intent

    def call_llm_with_tools(self, state: AgentState):
        self._emit_progress("call_llm_with_tools", "🤖 AI is analyzing...")
        
        print("--- Calling LLM with Tools ---")
        current_messages = state['messages']
        
        # Get the intent from state and select appropriate system prompt and tools
        intent = state.get("intent", "general_qa_agent")
        system_prompt = self._get_system_prompt_for_intent(intent)
        intent_tools = self._get_tools_for_intent(intent)
        print(f"Using system prompt for intent: {intent} with {len(intent_tools)} tools")

        # Create a temporary model with intent-specific tools
        intent_model = self.llm.bind_tools(intent_tools)

        # Use the intent-specific prompt to prepare messages
        message_to_send_to_model = self._prepare_messages_for_llm(
            current_messages=current_messages,
            system_prompt=system_prompt,
            max_human_interactions=5 
        )

        print("Messages being sent to LLM:")
        for msg_idx, msg in enumerate(message_to_send_to_model):
            print(f"  - Index: {msg_idx}, Type: {type(msg).__name__}")
            if isinstance(msg, ToolMessage):
                 print(f"    Tool Call ID: {msg.tool_call_id}")
                 print(f"    Tool Name: {msg.name}")
                 content_str = str(msg.content)
                 print(f"    Tool Content: {content_str[:200]}{'...' if len(content_str) > 200 else ''}")
            elif isinstance(msg, AIMessage) and msg.tool_calls:
                 content_preview = str(msg.content).replace('\n', ' ')[:100]
                 print(f"    Content: {content_preview}...")
                 print(f"    Tool Calls: {msg.tool_calls}")
            else:
                 content_preview = str(msg.content).replace('\n', ' ')[:100]
                 print(f"    Content: {content_preview}...")

        print(f"Calling model with {len(message_to_send_to_model)} messages: {[m.type for m in message_to_send_to_model]}")
        llm_response_message = intent_model.invoke(message_to_send_to_model)
        print(f"LLM response type: {llm_response_message.type}")
        if hasattr(llm_response_message, 'tool_calls') and llm_response_message.tool_calls:
             print(f"LLM requested tool calls: {llm_response_message.tool_calls}")
        else:
             print("LLM did not request tool calls.")

        return {'messages': [llm_response_message]}

    def route_after_llm_call(self, state: AgentState):
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
                    return "clarification_node"
            
            if any(tc.get('name') != self.request_clarification_tool.name for tc in last_message.tool_calls):
                print("Actionable tool(s) called by LLM, routing to 'action' node.")
                return "action"
        else:
            print("LLM did not produce any tool calls.")

        print("No actionable tools called by LLM or LLM provided a direct answer. Ending turn or processing direct answer.")
        return END

    def clarification_node(self, state: AgentState):
        self._emit_progress("clarification_node", "❓ Need more details...")
        
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

        question_to_user = get_natural_clarification_question(self.router_llm, original_tool, missing_param)
        
        tool_response_message = ToolMessage(
            content=f"Clarification for {original_tool} regarding {missing_param} is being requested from the user.",
            tool_call_id=tool_call_id_to_respond_to
        )
        
        ai_question_message = AIMessage(content=question_to_user)

        return {'messages': [tool_response_message, ai_question_message]}

    def take_action(self, state: AgentState):
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

        # Tool-specific progress messages
        tool_progress_map = {
            'show_flights': "✈️ Searching flights...",
            'plan_da_nang_trip': "📝 Creating itinerary...",
            'search_places_rag_tool': "📍 Finding places...",
            'search_places_rag': "📍 Finding places...",
            'tavily_search': "🔍 Gathering information...",
            'tavily_search_results_json': "🔍 Gathering information...",
            'select_flight_tool': "✅ Selecting flight..."
        }

        for t in tool_calls:
            tool_call_id = t.get('id')
            if not tool_call_id:
                print(f"Warning: Tool call missing 'id': {t}. Skipping.")
                continue

            tool_name = t.get('name')
            tool_args = t.get('args', {})
            
            # Emit tool-specific progress
            progress_message = tool_progress_map.get(tool_name, f"🔧 Using {tool_name}...")
            self._emit_progress("action", progress_message, tool_name=tool_name)
            
            print(f"Attempting to call tool: {tool_name} with args: {tool_args} (Call ID: {tool_call_id})")
            result_content_for_message = f"Error: Tool {tool_name} execution failed." # Default

            if tool_name == self.select_flight_tool.name:
                print(f"Processing '{self.select_flight_tool.name}'...")
                available_flights = current_information.get('available_flights')
                if not available_flights or not isinstance(available_flights, list):
                    result_content_for_message = "Error: No available flights found in my memory to select from. Please search for flights first."
                    print(f"Error for {tool_name}: {result_content_for_message}")
                    current_final_data = None
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
                    if tool_name == self.planner_tool.name:
                        attempting_modification = False
                        if tool_args.get('user_intention') == "modify":
                            attempting_modification = True
                            print(f"Planner modification: 'user_intention' is 'modify'. Proceeding with state injection.")
                        elif tool_args.get('user_intention') != "create" and 'existing_plan_json' in tool_args and current_information.get('current_trip_plan'):
                            attempting_modification = True
                            print(f"Planner modification HEURISTIC: LLM provided 'existing_plan_json' (and intent was not explicitly 'create') and state has a plan. Forcing state injection.")

                        if attempting_modification:
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
                            
                        if 'user_intention' in tool_args:
                            print(f"Removing 'user_intention' from tool_args before calling the tool. Value was: {tool_args['user_intention']}")
                            tool_args.pop('user_intention', None)
                        
                        print(f"Planner logic complete. Final tool_args keys for tool call: {list(tool_args.keys())}")
                    
                    if isinstance(tool_args, dict):
                        raw_result = tool_to_use.invoke(tool_args)
                    else:
                         raw_result = tool_to_use.invoke(tool_args)

                    if tool_name == self.flight_tool.name:
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
                                else:
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
                            else:
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
                    
                    elif tool_name == self.planner_tool.name:
                        try:
                            parsed_data = json.loads(raw_result)
                            if isinstance(parsed_data, dict) and parsed_data and not parsed_data.get('error'):
                                current_final_data = parsed_data 
                                current_final_tool_name = tool_name
                                current_information['current_trip_plan'] = parsed_data
                                result_content_for_message = raw_result 
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

                    else: 
                        if not isinstance(raw_result, str):
                            result_content_for_message = str(raw_result)
                        else:
                             result_content_for_message = raw_result
                        tool_messages_to_return.append(ToolMessage(tool_call_id=tool_call_id, name=tool_name, content=result_content_for_message))
                
                except Exception as e:
                    print(f"Error invoking/processing tool {tool_name} with args {tool_args}: {e}")
                    traceback.print_exc()
                    result_content_for_message = f"Error executing tool {tool_name}: {e}"
                    tool_messages_to_return.append(ToolMessage(tool_call_id=tool_call_id, name=tool_name, content=result_content_for_message))
                    current_final_data = None 
                    current_final_tool_name = None
            else:
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
        final_data = state.get("final_response_data")
        final_tool_name = state.get("final_response_tool_name")

        if final_data is not None:
            if final_tool_name == "confirmed_flight_selection":
                print("Routing after action: Flight selection confirmed. Continuing to LLM for final message formulation.")
                return "continue"
            elif final_tool_name == self.planner_tool.name:
                print(f"Routing after action: '{self.planner_tool.name}' tool executed. Data prepared. Continuing to LLM for response formulation.")
                return "continue"
            else:
                print(f"Routing after action: final_response_data found from tool '{final_tool_name}'. Finishing.")
                return "finish"
        else:
            print("Routing after action: No final_response_data. Continuing to LLM.")
            return "continue"

    def mark_not_related_node(self, state: AgentState):
        print("Query marked as not related to Da Nang travel.")
        return {"messages": [AIMessage(content="I apologize, but I specialize only in travel related to Da Nang, Vietnam, including planning trips there and checking flights from major Vietnamese cities. I cannot answer questions outside this scope.")]}

    def retrieve_stored_information(self, state: AgentState):
        self._emit_progress("retrieve_stored_information", "💾 Retrieving saved info...")
        
        print("---RETRIEVING STORED INFORMATION---")
        messages = state['messages']
        last_human_message = messages[-1]
        if not isinstance(last_human_message, HumanMessage):
            return {"messages": [AIMessage(content="I need your request to retrieve information.")], "final_response_tool_name": "error_no_human_message"}

        user_query = last_human_message.content.lower()
        information = state.get('information', {})
        response_message = "I couldn't find the specific information you asked for in my current memory."
        retrieved_data_type = "retrieved_nothing"

        if ("booked" in user_query or "confirmed" in user_query or "selected flight" in user_query) and information.get('confirmed_booking_details'):
            response_message = f"Okay, here is the confirmed flight detail I have for you."
            retrieved_data_type = "retrieved_flight_details"

        elif ("available flights" in user_query or "flights again" in user_query or "show flights" in user_query) and information.get('available_flights'):
            flights = information['available_flights']
            if flights:
                response_message = f"Okay, here are the {len(flights)} flight options I found previously."
                retrieved_data_type = "retrieved_available_flights"
            else:
                response_message = "I found no available flights previously."
                retrieved_data_type = "retrieved_no_available_flights"

        elif ("plan" in user_query or "itinerary" in user_query) and information.get('current_trip_plan'):
            response_message = f"Okay, here is the current trip plan we discussed."
            retrieved_data_type = "retrieved_plan"

        elif retrieved_data_type == "retrieved_nothing":
             if information:
                 response_message = "I found some information stored for our conversation, but not the specific item you asked for. Here is what I have:"
                 retrieved_data_type = "retrieved_generic_info"
             else:
                 response_message = "I don't have any specific information stored for our current conversation yet."

        return {
            "messages": [AIMessage(content=response_message)],
            "final_response_tool_name": retrieved_data_type
            }

    def run_conversation(self, query: str, thread_id: str | None = None):
        # Set the current thread_id for progress tracking
        self._current_thread_id = thread_id
        print(f"[Agent] Set current thread ID for progress tracking: {thread_id}")
        
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
                     initial_persistent_information = retrieved_info
                     print(f"Loaded existing information from memory for thread {thread_id}")

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
                    # final_ai_message_content = f"Tool execution resulted in: {final_graph_message_obj.content}"
                    final_ai_message_content = f"{final_graph_message_obj.content}"

                    logging.warning(f"Graph ended with ToolMessage for thread {thread_id}: {final_graph_message_obj.content}")
                else:
                    final_ai_message_content = f"Conversation ended unexpectedly. Last message type: {type(final_graph_message_obj).__name__}"
                    logging.error(f"Graph ended with unexpected message type for thread {thread_id}: {type(final_graph_message_obj).__name__}")
            else:
                logging.error(f"Graph execution for {thread_id} finished with empty or invalid final state messages.")

            response_payload = prepare_response_payload(final_state, final_ai_message_content, thread_id, self.request_clarification_tool.name)

        except Exception as e:
             print(f"Critical Error during graph execution for query '{query}' in thread {thread_id}: {e}")
             traceback.print_exc()
             response_payload = {
                 "response": {"message": f"Error during processing: {str(e)}"},
                 "intent": "error",
                 "thread_id": thread_id,
                 "type": "Error"
             }
        finally:
            # Complete progress and cleanup
            if self._current_thread_id:
                progress_manager.complete_progress(self._current_thread_id, "✅ Done!")
                self._current_thread_id = None

        print(f"--- Returning response payload for thread {thread_id}: Intent='{response_payload['intent']}', Type='{response_payload['type']}' ---")
        return response_payload


    
    
