import os
import traceback
import operator
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_openai import ChatOpenAI
from langchain_core.messages import AnyMessage, SystemMessage, HumanMessage, ToolMessage, AIMessage
from typing import TypedDict, Annotated, Optional
from langchain_community.tools.tavily_search import TavilySearchResults
import sqlite3
load_dotenv()

sqlite_conn = sqlite3.connect("checkpoints.sqlite", check_same_thread=False)
memory = SqliteSaver(sqlite_conn)

class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    relevance_decision: Optional[str]
    query_type: Optional[str]  # 'persona', 'history', 'content'
    needs_search: Optional[bool]  # True if search is needed, False otherwise

class Agent:
    def __init__(self):
        self.system =  """You are a smart research assistant specialized in Da Nang travel. Use the search engine to look up information relevant to Da Nang travel. \
You are allowed to make multiple calls (either together or in sequence). \
Only look up information when you are sure of what you want. \
If you need to look up some information before asking a follow up question, you are allowed to do that! \
Answer questions only if they are related to travel in Da Nang, Vietnam.
"""
        self.llm = ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0,
                api_key=os.getenv("OPENAI_API_KEY")
            )
        self.model = self.llm.bind_tools([TavilySearchResults(max_results=2)])

        self.relevance_llm = ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0,
                api_key=os.getenv("OPENAI_API_KEY")
            )

        self.graph = StateGraph(AgentState)
        self.graph.add_node("initial_router", self.initial_router)
        self.graph.add_node("direct_llm_answer", self.direct_llm_answer)
        self.graph.add_node("relevance_checker", self.check_relevance)
        self.graph.add_node("llm_decide_search", self.llm_decide_search)
        self.graph.add_node("search_router", self.search_router)
        self.graph.add_node("call_llm_with_search", self.call_llm_with_search)
        self.graph.add_node("call_llm_without_search", self.call_llm_without_search)
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
                "continue": "llm_decide_search",
                "end": "mark_not_related"
            }
        )
        self.graph.add_conditional_edges(
            "llm_decide_search",
            self.route_based_on_search_decision,
            {
                "search": "call_llm_with_search",
                "no_search": "call_llm_without_search"
            }
        )
        self.graph.add_conditional_edges("call_llm_with_search", self.exists_action, {True: "action", False: END})
        self.graph.add_edge("action", "call_llm_with_search")
        self.graph.add_edge("call_llm_without_search", END)
        self.graph.add_edge("direct_llm_answer", END)
        self.graph.add_edge("mark_not_related", END)

        self.memory = memory
        self.graph = self.graph.compile(checkpointer=self.memory)
        self.tavily_search = TavilySearchResults(max_results=2)
        self.tools = {t.name: t for t in [self.tavily_search]}

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
            response = self.relevance_llm.invoke([routing_prompt, user_message])
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
            response = self.relevance_llm.invoke([relevance_prompt, user_message])
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

    def llm_decide_search(self, state: AgentState):
        """Decides if a web search is needed for the query."""
        user_message = state['messages'][-1]
        if not isinstance(user_message, HumanMessage):
             print("Warning: Expected last message to be HumanMessage for search decision.")
             return {"needs_search": True}

        search_prompt = SystemMessage(content="""Does the following user query require a web search to answer accurately?
Respond only with 'search' if a search is needed, or 'no_search' if it can be answered without searching.""")

        try:
            response = self.relevance_llm.invoke([search_prompt, user_message])
            decision = response.content.strip().lower()
            print(f"Search decision for query '{user_message.content[:50]}...': {decision}")
            if decision not in ["search", "no_search"]:
                print(f"Warning: Search decision returned unexpected value: {decision}. Defaulting to 'search'.")
                decision = "search"
        except Exception as e:
             print(f"Error during search decision: {e}")
             traceback.print_exc()
             decision = "search"

        return {"needs_search": decision == "search"}

    def route_based_on_search_decision(self, state: AgentState):
        """Routes based on the search decision."""
        needs_search = state.get("needs_search")
        if needs_search is not None:
             print(f"Routing based on search decision: {needs_search}")
             return "search" if needs_search else "no_search"
        else:
             print("Warning: Search decision not found in state. Defaulting to 'search'.")
             return "search"

    def call_llm_with_search(self, state: AgentState):
        """Calls the LLM with tools bound."""
        messages = state['messages']
        if not any(isinstance(m, SystemMessage) for m in messages):
             messages = [SystemMessage(content=self.system)] + messages
        message = self.model.invoke(messages)
        return {'messages': [message]}

    def call_llm_without_search(self, state: AgentState):
        """Calls the LLM without tools bound."""
        messages = state['messages']
        if not any(isinstance(m, SystemMessage) for m in messages):
             messages = [SystemMessage(content=self.system)] + messages
        message = self.llm.invoke(messages)
        return {'messages': [message]}

    def exists_action(self, state: AgentState):
        last_message = state['messages'][-1]
        has_tools = hasattr(last_message, 'tool_calls') and len(last_message.tool_calls) > 0
        print(f"Checking for actions: {has_tools}")
        return has_tools

    def take_action(self, state: AgentState):
        tool_calls = state['messages'][-1].tool_calls
        results = []
        for t in tool_calls:
            print(f"Calling tool: {t['name']} with args {t['args']}")
            if t['name'] == self.tavily_search.name:
                 try:
                    result = self.tavily_search.invoke(t['args'])
                    results.append(ToolMessage(tool_call_id=t['id'], name=t['name'], content=str(result)))
                 except Exception as e:
                    print(f"Error invoking tool {t['name']}: {e}")
                    results.append(ToolMessage(tool_call_id=t['id'], name=t['name'], content=f"Error: Tool failed with {e}"))
            else:
                 print(f"Warning: Tool '{t['name']}' not found.")
                 results.append(ToolMessage(tool_call_id=t['id'], name=t['name'], content=f"Error: Tool '{t['name']}' not found."))

        print("Back to the model!")
        return {'messages': results}

    def mark_not_related_node(self, state: AgentState):
        """Sets the final message to 'Not Related'."""
        print("Query marked as not related.")
        return {"messages": [AIMessage(content="Not Related")]}

    def search_router(self, state: AgentState):
        """Routes based on the search decision."""
        needs_search = state.get("needs_search")
        if needs_search is not None:
             print(f"Routing based on search decision: {needs_search}")
             return "search" if needs_search else "no_search"
        else:
             print("Warning: Search decision not found in state. Defaulting to 'search'.")
             return "search"

    def run_conversation(self, query: str):
        messages = [HumanMessage(content=query)]
        import uuid
        thread_id = str(uuid.uuid4())
        thread = {"configurable": {"thread_id": thread_id}}
        print(f"\n--- Running conversation for thread {thread_id} ---")
        print(f"Initial query: {query}")
        try:
            initial_state = {"messages": messages, "relevance_decision": None, "query_type": None, "needs_search": None}
            result = self.graph.invoke(initial_state, config=thread)

            if result and 'messages' in result and result['messages']:
                 final_message = result['messages'][-1]
                 print(f"Final message content: {final_message.content}")
                 return final_message.content
            else:
                 print("Error: Graph execution finished with no messages in the final state.")
                 return "Error: No final message."
        except Exception as e:
             print(f"Error during graph execution for query '{query}': {e}")
             traceback.print_exc()
             return f"Error: {e}"
    
    
