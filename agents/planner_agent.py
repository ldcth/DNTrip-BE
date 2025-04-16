# agents/planner_agent.py
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents import AgentExecutor, create_openai_functions_agent
from typing import List
import os
from dotenv import load_dotenv

# Import tools from tools.py
from .tools import all_tools # Assuming tools.py is in the parent directory

load_dotenv()

def create_planner_agent(llm: ChatOpenAI, tools: list):
    """Creates the travel planner agent."""
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a helpful travel planning assistant. "
                "Your goal is to understand the user's request, use the available tools to gather information (flights, hotels), "
                "and create a coherent travel plan. Ask clarifying questions if needed. "
                "Once you have enough information from the tools, summarize the plan for the user. "
                "You have access to the following tools:",
            ),
            MessagesPlaceholder(variable_name="messages"), # For conversation history
            MessagesPlaceholder(variable_name="agent_scratchpad"), # For agent's internal thoughts/tool calls
        ]
    )
    agent = create_openai_functions_agent(llm, tools, prompt)
    agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True) # Set verbose=True for debugging
    return agent_executor