# Import necessary Flask libraries and extensions
from flask import Flask, request, jsonify, Response
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager
from flask_cors import CORS
import os
from dotenv import load_dotenv 
import uuid
import json
from agents.llm import LLMAgent # Keep if needed for /api/ask
from agents.graph import Agent
from agents.progress_manager import progress_manager
from database.user import Users
from database.conversation import Conversations
from database.content import Contents
from datetime import timedelta
import subprocess
import sys
import threading
import schedule
import time

from flask_jwt_extended import (
    JWTManager,
    jwt_required,
    create_access_token,
    get_jwt_identity,
)
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

scheduler_running = False

def run_flight_scraper():
    """Run the flight scraper script"""
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        script_path = os.path.join(current_dir, 'scrapper', 'flight_kayak_final.py')
        subprocess.run([sys.executable, script_path], cwd=current_dir)
        print(f"✅ Flight scraper completed at {time.strftime('%H:%M:%S')}")
    except Exception as e:
        print(f"❌ Error running flight scraper: {str(e)}")

def setup_scheduler():
    """Set up daily midnight scheduler"""
    global scheduler_running
    if not scheduler_running:
        schedule.every().day.at("00:40").do(run_flight_scraper)
        scheduler_running = True
        threading.Thread(target=lambda: [schedule.run_pending() or time.sleep(60) for _ in iter(int, 1)], daemon=True).start()
        print("✅ Flight scraper scheduled for daily midnight runs")

@app.route('/api/cron/run-now', methods=['POST'])
def run_now():
    """Manually trigger flight scraper"""
    try:
        threading.Thread(target=run_flight_scraper, daemon=True).start()
        return jsonify({"message": "Flight scraper started", "status": "success"}), 200
    except Exception as e:
        return jsonify({"error": str(e), "status": "error"}), 500


@app.route("/")
def index():
    """Basic index route."""
    return "123" # Keep your existing index route

@app.post("/api/auth/create")
def create_account():
    data = request.json
    user = Users()
    res = user.find_by_email(data["email"])
    if res:
        return jsonify({"message": "This email is already used!"}), 400
    else:
        user.name = data["name"]
        user.email = data["email"]
        hashed_password = bcrypt.generate_password_hash(data["password"]).decode(
            "utf-8"
        )
        user.password = hashed_password
        user.role = 1
        user.save_to_db()
        return jsonify(user.__dict__), 200

@app.post("/api/auth/login")
def login():
    data = request.json
    user = Users()
    check = user.find_by_email(data["email"])
    if check:
        is_valid = bcrypt.check_password_hash(user.password, data["password"])
        if is_valid:
            access_token = create_access_token(
                identity=user._id, expires_delta=timedelta(days=30)
            )
            return jsonify({"user": user.__dict__, "access_token": access_token}), 200
        else:
            return jsonify({"message": "Invalid email or password"}), 401
    else:
        return jsonify({"message": "Invalid email or password"}), 401


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
        return jsonify({"response": response, "type": "AI"})

    except Exception as e:
        # Handle potential errors
        print(f"[/api/ask] Error: {str(e)}")
        return jsonify({"error": str(e), "type": "Error"}), 500


# --- NEW Endpoint for the LangGraph Travel Planner ---
@app.route('/api/chat', methods=['POST'])
def handle_travel_chat():
    """Handles chat requests for travel planning using the Agent instance."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON payload"}), 400

    query = data.get('question')
    thread_id = data.get('thread_id') 

    # Validate that both question and thread_id are present
    if not query:
        return jsonify({"error": "Missing 'question' in request"}), 400
    if not thread_id:
        return jsonify({"error": "Missing 'thread_id' in request"}), 400

    print(f"[/api/chat] Continuing conversation with thread_id: {thread_id}")

    # Call the agent, passing the thread_id
    agent_result = travel_planner_instance.run_conversation(query, thread_id=thread_id)

    returned_thread_id = agent_result.get("thread_id", thread_id) 
    response_content = agent_result.get("response", "Error: No response content found.")
    intent = agent_result.get("intent", "unknown") # Get the intent

    print(f"[/api/chat] Intent: {intent}, Assistant Response: {response_content}")

    if intent == "error" or str(response_content).startswith(("Error:", "An error occurred:")):
        return jsonify({"error": response_content, "intent": "error", "thread_id": returned_thread_id, "type": "Error"}), 500

    # Return the successful response including the intent and returned thread_id
    return jsonify({"response": response_content, "intent": intent, "thread_id": returned_thread_id, "type": "AI"})

# --- Health Check Endpoint (Optional but Recommended) ---
@app.route('/health', methods=['GET'])  
def health_check():
    """Provides a simple health check endpoint for monitoring."""
    travel_app_status = "OK" if travel_planner_instance and travel_planner_instance.graph else "Error: Travel App not initialized"
    return jsonify({
        "status": "OK", # Overall status of the Flask app itself
        "components": {
            "travel_planner": travel_app_status
        }
    })

# --- SSE Progress Endpoint ---
@app.route('/api/chat/progress/<thread_id>', methods=['GET'])
def stream_progress(thread_id):
    """Stream real-time progress updates for a conversation thread using SSE."""
    def generate():
        try:
            for event in progress_manager.get_progress_generator(thread_id):
                yield event
        except Exception as e:
            print(f"[SSE] Error streaming progress for thread {thread_id}: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    response = Response(generate(), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['Connection'] = 'keep-alive'
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Cache-Control'
    
    return response

@app.route('/api/user/chat', methods=['POST'])
@jwt_required()
def user_travel():
    """Handles travel requests for authenticated users."""
    data = request.get_json()
    user_id = get_jwt_identity()
    print(f"[/api/user/chat] User: {user_id}")
    if not data:
        return jsonify({"error": "Invalid JSON payload"}), 400

    query = data.get('question')
    thread_id = data.get('thread_id') 

    # Validate that both question and thread_id are present
    if not query:
        return jsonify({"error": "Missing 'question' in request"}), 400
    if not thread_id:
        return jsonify({"error": "Missing 'thread_id' in request"}), 400

    print(f"[/api/user/chat] Continuing conversation with thread_id: {thread_id}")

    # Call the agent, passing the thread_id
    agent_result = travel_planner_instance.run_conversation(query, thread_id=thread_id)

    returned_thread_id = agent_result.get("thread_id", thread_id) 
    response_content = agent_result.get("response", "Error: No response content found.")
    intent = agent_result.get("intent", "unknown") # Get the intent

    print(f"[/api/user/chat] Intent: {intent}, Assistant Response: {response_content}")

    if intent == "error" or str(response_content).startswith(("Error:", "An error occurred:")):
        return jsonify({"error": response_content, "intent": "error", "thread_id": returned_thread_id, "type": "Error"}), 500

    # Return the successful response including the intent and returned thread_id
    conversation = Conversations(user_id, [], query, returned_thread_id)
    if data["thread_id"] != "":
        print("here")
        conversation.find_by_thread_id(data["thread_id"])
    else:
        conversation.save_to_db()
    contentId = conversation.contents
    human_content = Contents(conversation._id, thread_id, query, "Human", "")
    human_content.save_to_db()

    contentId.append(human_content._id)
    ai_content = Contents(conversation._id, thread_id, response_content, "AI", intent)
    ai_content.save_to_db()
    contentId.append(ai_content._id)

    conversation.contents = contentId
    conversation.save_to_db()

    return jsonify({"response": response_content, "intent": intent, "thread_id": returned_thread_id, "type": "AI", "conversationId": conversation._id})

@app.route("/api/user/conversation", methods=["GET"])
@jwt_required()
def get_user_conversation():
    user_id = get_jwt_identity()
    conversation = Conversations()
    res = conversation.find_by_user_id(user_id)

    return jsonify(res), 200

@app.route("/api/user/conversation/<id>", methods=["GET"])
@jwt_required()
def get_conversation_content(id):
    conversation = Conversations()
    conversation.find_by_id(id)
    data = []
    for text in conversation.contents:
        content = Contents()
        content.find_by_id(text)
        data.append(content.__dict__)

    return jsonify(data), 200


# --- Main execution block ---
if __name__ == "__main__":
    print("🚀 Starting Flask application...")
    # setup_scheduler()
    app.run(debug=True, port=3001, host="0.0.0.0")