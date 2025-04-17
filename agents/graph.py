import os
import traceback
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_openai import ChatOpenAI
from langchain_core.messages import AnyMessage, SystemMessage, HumanMessage, ToolMessage, AIMessage
from langchain_community.tools.tavily_search import TavilySearchResults
from agents.state import AgentState
from agents.tools import plan_da_nang_trip_tool
import sqlite3

load_dotenv()

sqlite_conn = sqlite3.connect("checkpoints.sqlite", check_same_thread=False)
memory = SqliteSaver(conn=sqlite_conn)

class Agent:
    def __init__(self):
        self.system =  """You are a smart research assistant specialized in Da Nang travel.
Use the search engine to look up specific, current information relevant to Da Nang travel (e.g., weather, specific opening hours, event details).
You can also plan detailed travel itineraries for Da Nang if the user asks for a plan and specifies a duration (e.g., 'plan a 3 days 2 nights trip', 'make a plan for 1 week'). Extract the travel duration accurately to use the planning tool.
If the user asks for a plan, use the 'plan_da_nang_trip' tool. For other information, use the search tool.
Answer questions only if they are related to travel in Da Nang, Vietnam.
If a query is relevant but doesn't require planning or searching external info, answer directly.
"""
        self.llm = ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0,
                api_key=os.getenv("OPENAI_API_KEY")
            )
        self.tavily_search = TavilySearchResults(max_results=2)
        self.planner_tool = plan_da_nang_trip_tool
        self.model = self.llm.bind_tools([self.tavily_search, self.planner_tool])

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
                "plan_trip": "call_llm_with_tools",
                "search_info": "call_llm_with_tools",
                "general_qa": "call_llm_with_tools",
                "error": END
            }
        )
        self.graph.add_conditional_edges(
            "call_llm_with_tools",
            self.exists_action,
            {True: "action", False: END}
        )
        self.graph.add_edge("action", "call_llm_with_tools")
        self.graph.add_edge("direct_llm_answer", END)
        self.graph.add_edge("mark_not_related", END)

        self.memory = memory
        self.graph = self.graph.compile(checkpointer=self.memory)
        self.tools = {t.name: t for t in [self.tavily_search, self.planner_tool]}

    def initial_router(self, state: AgentState):
        """Routes the query based on its type."""
        user_message = state['messages'][-1]
        if not isinstance(user_message, HumanMessage):
             print("Warning: Expected last message to be HumanMessage for initial routing.")
             return {"query_type": "content"}

        routing_prompt = SystemMessage(content="""Classify the following user query into one of these categories:
- 'persona': Questions about the bot's identity or capabilities (e.g., 'Who are you?', 'What can you do?')
- 'history': Questions about the conversation history (e.g., 'What was my last question?')
- 'content': Any other type of question.
Respond only with the category name.""")

        try:
            response = self.router_llm.invoke([routing_prompt, user_message])
            query_type = response.content.strip().lower()
            print(f"Initial routing for query '{user_message.content[:50]}...': {query_type}")
            if query_type not in ["persona", "history", "content"]:
                print(f"Warning: Initial routing returned unexpected value: {query_type}. Defaulting to 'content'.")
                query_type = "content"
        except Exception as e:
             print(f"Error during initial routing: {e}")
             traceback.print_exc()
             query_type = "content"

        return {"query_type": query_type}

    def route_based_on_query_type(self, state: AgentState):
        """Routes based on the query type."""
        query_type = state.get("query_type")
        if query_type:
             print(f"Routing based on query type: {query_type}")
             return query_type
        else:
             print("Warning: Query type not found in state. Defaulting to 'content'.")
             return "content"

    def direct_llm_answer(self, state: AgentState):
        """Answers persona or history questions directly using the LLM."""
        messages = state['messages']
        if not any(isinstance(m, SystemMessage) for m in messages):
             messages = [SystemMessage(content=self.system)] + messages
        message = self.llm.invoke(messages)
        return {'messages': [message]}

    def check_relevance(self, state: AgentState):
        """Checks if the user query is related to Da Nang travel."""
        user_message = state['messages'][-1]
        if not isinstance(user_message, HumanMessage):
             print("Warning: Expected last message to be HumanMessage for relevance check.")
             return {"relevance_decision": "end"}

        relevance_prompt = SystemMessage(content="""Is the following user query related to travel in Da Nang, Vietnam?
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
             print(f"Routing based on decision: {decision}")
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

        intent_prompt = SystemMessage(content="""Given the user query about Da Nang travel, classify the primary intent:
- 'plan_trip': User wants a travel plan/itinerary (e.g., 'plan a trip', 'make an itinerary').
- 'search_info': User is asking a question likely requiring external, up-to-date information (weather, opening hours, specific events, prices).
- 'general_qa': User is asking a general question about Da Nang that might be answerable from general knowledge or conversation history.
Respond only with 'plan_trip', 'search_info', or 'general_qa'.""")

        try:
            response = self.router_llm.invoke([intent_prompt, user_message])
            intent = response.content.strip().lower()
            print(f"Intent routing for query '{user_message.content[:50]}...': {intent}")
            if intent not in ["plan_trip", "search_info", "general_qa"]:
                print(f"Warning: Intent routing returned unexpected value: {intent}. Defaulting to 'general_qa'.")
                intent = "general_qa"
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
            return intent
        else:
            print("Warning: Intent not found in state. Defaulting to error.")
            return "error"

    def call_llm_with_tools(self, state: AgentState):
        """Calls the main LLM bound with planning and search tools."""
        print("--- Calling LLM with Tools ---")
        messages = state['messages']
        if not any(isinstance(m, SystemMessage) for m in messages):
             messages = [SystemMessage(content=self.system)] + messages
        message = self.model.invoke(messages)
        return {'messages': [message]}

    def exists_action(self, state: AgentState):
        last_message = state['messages'][-1]
        has_tools = isinstance(last_message, AIMessage) and \
                    hasattr(last_message, 'tool_calls') and \
                    last_message.tool_calls is not None and \
                    len(last_message.tool_calls) > 0
        print(f"Checking for actions: {has_tools}")
        return has_tools

    def take_action(self, state: AgentState):
        """Executes tools based on the LLM's request."""
        last_message = state['messages'][-1]
        if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
             print("Error: take_action called without valid tool calls in the last message.")
             return {'messages': [AIMessage(content="Internal error: Tried to take action without valid tool calls.")]}

        tool_calls = last_message.tool_calls
        results = []
        for t in tool_calls:
            tool_name = t['name']
            tool_args = t['args']
            print(f"Attempting to call tool: {tool_name} with args {tool_args}")
            if tool_name in self.tools:
                tool_to_use = self.tools[tool_name]
                try:
                    result = tool_to_use.invoke(tool_args)
                    results.append(ToolMessage(tool_call_id=t['id'], name=tool_name, content=str(result)))
                except Exception as e:
                    print(f"Error invoking tool {tool_name}: {e}")
                    traceback.print_exc()
                    results.append(ToolMessage(tool_call_id=t['id'], name=tool_name, content=f"Error: Tool failed with {e}"))
            else:
                 print(f"Warning: Tool '{tool_name}' not found in available tools.")
                 results.append(ToolMessage(tool_call_id=t['id'], name=tool_name, content=f"Error: Tool '{tool_name}' not found."))

        print("--- Action Results ---")
        for res in results:
            print(f"  Tool {res.name} ({res.tool_call_id}): {res.content[:200]}...")
        print("--- Returning to LLM ---")
        return {'messages': results}

    def mark_not_related_node(self, state: AgentState):
        """Sets the final message to 'Not Related'."""
        print("Query marked as not related.")
        return {"messages": [AIMessage(content="I specialize only in Da Nang travel. I cannot answer that question.")]}

    def run_conversation(self, query: str):
        messages = [HumanMessage(content=query)]
        import uuid
        thread_id = str(uuid.uuid4())
        thread = {"configurable": {"thread_id": thread_id}}
        print(f"\n--- Running conversation for thread {thread_id} ---")
        print(f"Initial query: {query}")
        try:
            initial_state = {"messages": messages, "relevance_decision": None, "query_type": None, "intent": None}
            final_state = self.graph.invoke(initial_state, config=thread)

            if final_state and 'messages' in final_state and final_state['messages']:
                 final_message = final_state['messages'][-1]
                 if isinstance(final_message, AIMessage):
                     content_to_return = final_message.content
                     print(f"Final message content (AIMessage): {content_to_return}")
                     return content_to_return
                 elif isinstance(final_message, ToolMessage):
                     print(f"Warning: Graph ended with a ToolMessage: {final_message.content}")
                     for msg in reversed(final_state['messages'][:-1]):
                         if isinstance(msg, AIMessage):
                             print(f"Returning content from previous AIMessage: {msg.content}")
                             return msg.content
                     return f"Tool Execution Result: {final_message.content}"
                 else:
                     print(f"Warning: Unexpected final message type: {type(final_message)}")
                     return str(final_message)
            else:
                 print("Error: Graph execution finished with no messages or empty message list in the final state.")
                 return "Error: No final message."
        except Exception as e:
             print(f"Error during graph execution for query '{query}': {e}")
             traceback.print_exc()
             return f"Error: {e}"
    
    
