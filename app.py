# Import necessary Flask libraries and extensions
from flask import Flask, request, jsonify
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager
from flask_cors import CORS
import os
from dotenv import load_dotenv # Import dotenv to load environment variables
import uuid
# Import custom modules
from agents.llm import LLMAgent # Keep if needed for /api/ask
# Import the NEW class from agents/graph.py
from agents.graph import Agent
load_dotenv()

# Initialize the Flask application
app = Flask(__name__, static_folder='public', static_url_path='')

# --- Flask App Configuration ---
app.config["SECRET_KEY"] = "FP" 
bcrypt = Bcrypt(app)
jwt = JWTManager(app)
CORS(app)


llm_agent = LLMAgent()

travel_planner_instance = Agent()

@app.route("/")
def index():
    """Basic index route."""
    return "123" # Keep your existing index route

# --- Endpoint for the original Simple LLM Agent ---
@app.route("/api/ask", methods=["POST"])
def ask_question():
    """Endpoint using the simple LLMAgent for general questions."""
    # ... (keep the existing code for this endpoint) ...
    try:
        # Get JSON data from the request
        data = request.get_json()
        question = data.get("question")
        print(f"[/api/ask] Question: {question}")
        # Basic validation
        if not question:
            return jsonify({"error": "Question is required"}), 400

        # Use the simple llm_agent instance
        response = llm_agent.get_response(question)
        print(f"[/api/ask] Response: {response}")
        # Return the response as JSON
        return jsonify({"response": response})

    except Exception as e:
        # Handle potential errors
        print(f"[/api/ask] Error: {str(e)}")
        return jsonify({"error": str(e)}), 500


# --- NEW Endpoint for the LangGraph Travel Planner ---
@app.route('/api/travel', methods=['POST'])
def handle_travel_chat():
    """Handles chat requests for travel planning using the Agent instance."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON payload"}), 400

    query = data.get('question')
    thread_id = data.get('thread_id') # Get thread_id from request

    # Validate that both question and thread_id are present
    if not query:
        return jsonify({"error": "Missing 'question' in request"}), 400
    if not thread_id:
        return jsonify({"error": "Missing 'thread_id' in request"}), 400

    print(f"[/api/travel] Continuing conversation with thread_id: {thread_id}")

    # Call the agent which now returns a dictionary
    agent_result = travel_planner_instance.run_conversation(query)
    response_content = agent_result.get("response", "Error: No response content found.")
    intent = agent_result.get("intent", "unknown") # Get the intent

    print(f"[/api/travel] Intent: {intent}, Assistant Response: {response_content}")

    # Check for errors based on intent or response content
    if intent == "error" or str(response_content).startswith(("Error:", "An error occurred:")):
         # Use the response_content which might contain a specific error message
        return jsonify({"error": response_content, "intent": "error", "thread_id": thread_id}), 500

    # Return the successful response including the intent
    return jsonify({"response": response_content, "intent": intent, "thread_id": thread_id})

# --- Health Check Endpoint (Optional but Recommended) ---
@app.route('/health', methods=['GET'])
def health_check():
    """Provides a simple health check endpoint for monitoring."""
    # Check the status based on the instance and its compiled app
    travel_app_status = "OK" if travel_planner_instance and travel_planner_instance.app else "Error: Travel App not initialized"
    # Return the overall status and status of individual components
    return jsonify({
        "status": "OK", # Overall status of the Flask app itself
        "components": {
            "travel_planner": travel_app_status
            # Add checks for other dependencies if needed
        }
    })


# --- Main execution block ---
if __name__ == "__main__":
    # Run the Flask development server
    app.run(debug=True, port=3001, host="0.0.0.0") # Keep your run configuration