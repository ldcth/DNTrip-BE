"""
Test script to verify the places_agent intent with the RAG tool.
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agents.graph import Agent

def test_places_agent():
    """Test the places_agent intent with the RAG tool."""
    
    print("=== Testing Places Agent Intent with RAG Tool ===")
    
    try:
        # Initialize the agent
        print("1. Initializing agent...")
        agent = Agent()
        print("   ✓ Agent initialized successfully")
        
        # Test queries that should trigger the places_agent intent
        test_queries = [
            "Find top 5 restaurants in Hai Chau district",
            "What are the best hotels near My Khe Beach?",
            "Show me cafes near Fivitel Da Nang Hotel",
            "Find highly rated seafood restaurants in Da Nang",
            "What are some budget-friendly accommodations in the city center?"
        ]
        
        for i, query in enumerate(test_queries, 1):
            print(f"\n{i}. Testing query: '{query}'")
            
            try:
                # Use a unique thread ID for each test
                thread_id = f"test_places_{i}"
                
                # Run the conversation
                response = agent.run_conversation(query, thread_id=thread_id)
                
                # Check if the response contains the expected intent
                if response and "intent" in response:
                    intent = response.get("intent")
                    print(f"   ✓ Detected intent: {intent}")
                    
                    if intent == "places_agent":
                        print("   ✓ Correctly identified as places_agent intent")
                    else:
                        print(f"   ⚠ Expected 'places_agent' intent but got '{intent}'")
                
                # Check if the response contains results
                if response and "response" in response and "message" in response["response"]:
                    message = response["response"]["message"]
                    print(f"   ✓ Got response (length: {len(message)})")
                    # Print first 200 characters of response
                    print(f"   Response preview: {message[:200]}...")
                else:
                    print("   ⚠ Empty or no response")
                    
            except Exception as e:
                print(f"   ✗ Query failed: {str(e)}")
        
        print("\n=== Places Agent Test COMPLETED ===")
        
    except Exception as e:
        print(f"✗ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("Starting Places Agent Test...\n")
    test_places_agent() 