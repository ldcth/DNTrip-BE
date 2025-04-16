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
from agents.graph import TravelPlannerGraph
from agents.graph_sample import Agent
load_dotenv()

# Initialize the Flask application
app = Flask(__name__, static_folder='public', static_url_path='')

# --- Flask App Configuration ---
app.config["SECRET_KEY"] = "FP" 
bcrypt = Bcrypt(app)
jwt = JWTManager(app)
CORS(app)

# --- Initialize Existing Simple LLM Agent ---
# Keep this if you still use the /api/ask endpoint
llm_agent = LLMAgent()

# --- Initialize LangGraph Travel Planner Application using the Class ---
# Database path for conversation state checkpointing
# DATABASE_PATH = os.environ.get("TRAVEL_DB_PATH", "travel_agent_conversations.sqlite")
# Initialize the planner graph instance variable to None initially
travel_planner_instance = Agent()

# travel_planner_instance = None
# try:
# #     # Create an instance of the TravelPlannerGraph class ONCE when the server starts
#     # travel_planner_instance = TravelPlannerGraph(db_path=DATABASE_PATH)
#     travel_planner_instance = Agent()
#     # Check if the internal app was compiled successfully during instantiation
#     # if not travel_planner_instance.app:
#     #      raise RuntimeError("TravelPlannerGraph internal app failed to compile.")
#     # print("--- Flask App: TravelPlannerGraph Initialized Successfully ---")
# except Exception as e:
#     # Log fatal error if TravelPlannerGraph instantiation fails
# #     print(f"FATAL: Could not initialize TravelPlannerGraph: {e}")
# #     # travel_planner_instance will remain None or have app=None

# --- Basic Routes ---

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
    if not query:
        return jsonify({"error": "Missing 'question' in request"}), 400

    thread_id = data.get('thread_id', "123")
    print(f"[/api/travel] {'New' if not data.get('thread_id') else 'Continuing'} conversation with thread_id: {thread_id}")

    assistant_response = travel_planner_instance.run_conversation(query)
    print(f"[/api/travel] Assistant Response: {assistant_response}")

    if isinstance(assistant_response, list):
        response_content = assistant_response[-1].content
    else:
        response_content = assistant_response

    if str(response_content).startswith(("Error:", "An error occurred:")):
        return jsonify({"error": response_content}), 500

    return jsonify({"response": response_content, "thread_id": thread_id})

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