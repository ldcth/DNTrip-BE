import os
import traceback
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, BaseMessage

# Assuming these imports are relative to the project structure
# If agents/graph.py is inside 'agents' folder, adjust paths if needed
from .state import TravelPlanState  # Needs to be accessible
from .planner_agent import create_planner_agent # Assuming planner_agent.py is in the same 'agents' folder
from .tools import all_tools # Needs to be accessible (maybe move tools.py outside agents?)

load_dotenv()

class TravelPlannerGraph:
    """
    Encapsulates the LangGraph setup and execution logic for the travel planner.
    """
    def __init__(self, db_path: str = "travel_agent_conversations.sqlite"):
        """
        Initializes the LLM, agent, tools, graph, and checkpointer upon instantiation.

        Args:
            db_path (str): Path to the SQLite database for checkpointing.
                           Use ":memory:" for in-memory storage.
        """
        print(f"--- Initializing TravelPlannerGraph (DB: {db_path}) ---")
        self.db_path = db_path
        self.app = None
        self.memory = None
        self._initialize_graph() # Call internal method to setup

    def _initialize_graph(self):
        """Internal method to set up all components of the graph."""
        try:
            # --- LLM Initialization ---
            llm = ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0,
                api_key=os.getenv("OPENAI_API_KEY")
            )

            # --- Agent Initialization ---
            # Pass the LLM and tools to the agent creation function
            planner_agent_executor = create_planner_agent(llm, all_tools)

            # --- Define Node (using the initialized agent executor) ---
            def planner_node(state: TravelPlanState):
                """Node that invokes the planner agent."""
                print("--- Planner Node ---")
                # Use the agent executor created above
                response = planner_agent_executor.invoke({"messages": state["messages"]})
                # Assuming the agent output needs to be added back as a message
                return {"messages": [response["output"]]}

            # --- Build the Graph ---
            workflow = StateGraph(TravelPlanState)
            workflow.add_node("planner", planner_node)
            workflow.set_entry_point("planner")
            workflow.add_edge("planner", END)

            # --- Compile the Graph with Checkpointing ---
            self.memory = SqliteSaver.from_conn_string(self.db_path)
            self.app = workflow.compile(checkpointer=self.memory)

            print(f"--- Travel App Compiled (Checkpointer: {self.db_path}) ---")

        except Exception as e:
            print(f"!!! Error during TravelPlannerGraph Initialization: {e}")
            traceback.print_exc()
            # Ensure self.app remains None if initialization fails
            self.app = None

    def run_conversation(self, query: str, thread_id: str) -> str:
        """
        Runs a query through the compiled LangGraph application for a specific conversation thread.

        Args:
            query (str): The user's input message.
            thread_id (str): The unique identifier for the conversation thread.

        Returns:
            str: The assistant's response message content.
                 Returns an error message string if the app isn't compiled or an error occurs.
        """
        if not self.app:
            return "Error: Travel Planner Application is not initialized."

        config = {"configurable": {"thread_id": thread_id}}
        input_message = HumanMessage(content=query)
        inputs = {"messages": [input_message]}

        try:
            print(f"\n--- Invoking App (Thread: {thread_id}) ---")
            # Invoke the compiled application stored in self.app
            final_state = self.app.invoke(inputs, config=config)

            # Extract the last message, assuming it's the assistant's response
            if final_state and "messages" in final_state and final_state["messages"]:
                last_message = final_state["messages"][-1]
                # Handle different possible message types in the state
                if isinstance(last_message, BaseMessage):
                    return last_message.content
                elif isinstance(last_message, str):
                    return last_message
                elif isinstance(last_message, tuple) and len(last_message) > 1:
                    return str(last_message[1]) # Convert content to string
                else:
                    print(f"Warning: Could not extract content from last message: {last_message}")
                    return "Error: Could not determine assistant response format."
            else:
                return "Error: No messages found in the final state."

        except Exception as e:
            print(f"Error running graph for thread {thread_id}: {e}")
            traceback.print_exc() # Print stack trace for debugging
            return f"An error occurred: {str(e)}"

