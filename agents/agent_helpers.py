from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_openai import ChatOpenAI

from agents.prompts import NATURAL_CLARIFICATION_PROMPT
from agents.state import AgentState

def get_natural_clarification_question(router_llm: ChatOpenAI, original_tool_name: str, missing_parameter_name: str) -> str:
    """Generates a more natural-sounding clarification question using an LLM."""
    print(f"--- Generating natural clarification question for tool: {original_tool_name}, missing: {missing_parameter_name} ---")
    
    prompt_messages = [
        SystemMessage(
            content=NATURAL_CLARIFICATION_PROMPT
        ),
        HumanMessage(
            content=f"Original Tool: '{original_tool_name}'\nMissing Parameter: '{missing_parameter_name}'\nGenerate a natural question:"
        )
    ]
    
    try:
        response = router_llm.invoke(prompt_messages)
        natural_question = response.content.strip()
        print(f"Generated natural question: {natural_question}")
        return natural_question
    except Exception as e:
        print(f"Error generating natural clarification question: {e}. Falling back to template.")
        return f"To help me with {original_tool_name}, I need a bit more information. Could you please provide the {missing_parameter_name}?"

def prepare_response_payload(final_state: AgentState, final_ai_message_content: str, thread_id: str | None, request_clarification_tool_name: str):
    response_data_for_payload = {"message": final_ai_message_content}
    determined_intent = "general_qa_agent"  # Default

    final_response_data_from_turn = final_state.get("final_response_data")
    final_tool_name_from_turn = final_state.get("final_response_tool_name")
    current_turn_graph_intent = final_state.get("intent")
    current_turn_query_type = final_state.get("query_type")
    current_turn_relevance = final_state.get("relevance_decision")
    persistent_information = final_state.get("information", {})
    # Safely access the last message if messages exist
    final_graph_message_obj = final_state['messages'][-1] if final_state.get('messages') else None

    if current_turn_relevance == "end":
        determined_intent = "not_related"
        response_data_for_payload["message"] = final_ai_message_content
    elif final_response_data_from_turn is not None:
        if final_tool_name_from_turn == "confirmed_flight_selection":
            determined_intent = "flight_selection_confirmed"
            response_data_for_payload["selected_flight_details"] = final_response_data_from_turn
            response_data_for_payload["message"] = final_ai_message_content
        elif final_tool_name_from_turn == 'plan_da_nang_trip':
            determined_intent = "plan_agent"
            response_data_for_payload["plan_details"] = final_response_data_from_turn
            
            planner_message_str = None
            if isinstance(final_response_data_from_turn, dict):
                notes = final_response_data_from_turn.get("notes", [])
                if isinstance(notes, list):
                    for note in notes:
                        if isinstance(note, str) and note.startswith("Planner Message:"):
                            planner_message_str = note.replace("Planner Message:", "").strip()
                            break
            response_data_for_payload["planner_message"] = planner_message_str

            if planner_message_str is not None:
                response_data_for_payload["message"] = planner_message_str
            else:
                response_data_for_payload["message"] = "The travel planner processed your request. Please review the plan details provided. A specific status message was not available in the notes."
            
            if isinstance(response_data_for_payload.get("plan_details"), dict):
                response_data_for_payload["plan_details"].pop("conversational_summary", None)

        elif final_tool_name_from_turn == "flights_found_summary":
            determined_intent = "flights_found_awaiting_selection"
            response_data_for_payload["flights"] = persistent_information.get('available_flights', [])
            response_data_for_payload["message"] = final_ai_message_content
        elif final_tool_name_from_turn in ["flights_not_found_summary", "flights_tool_error_or_message", "flights_tool_format_error", "flights_tool_processing_error"]:
            determined_intent = "flight_search_direct_message"
            response_data_for_payload["message"] = final_ai_message_content
        elif final_tool_name_from_turn:
            determined_intent = "tool_result"
            response_data_for_payload[f"{final_tool_name_from_turn}_data"] = final_response_data_from_turn
            response_data_for_payload["message"] = final_ai_message_content
        else: 
            determined_intent = "unknown_tool_result_with_data"
            response_data_for_payload["data"] = final_response_data_from_turn
            response_data_for_payload["message"] = final_ai_message_content
    else:
        response_data_for_payload["message"] = final_ai_message_content
        if current_turn_query_type in ["persona", "history"]:
            determined_intent = "direct_answer"
        elif current_turn_graph_intent == "retrieve_information":
            determined_intent = "retrieve_information"
            if final_tool_name_from_turn == "retrieved_flight_details" and persistent_information.get('confirmed_booking_details'):
                response_data_for_payload["confirmed_flight_details"] = persistent_information['confirmed_booking_details']
            elif final_tool_name_from_turn == "retrieved_available_flights" and persistent_information.get('available_flights'):
                response_data_for_payload["flights"] = persistent_information['available_flights']
            elif final_tool_name_from_turn == "retrieved_plan" and persistent_information.get('current_trip_plan'):
                response_data_for_payload["plan_details"] = persistent_information['current_trip_plan']
            elif final_tool_name_from_turn == "retrieved_generic_info":
                response_data_for_payload["stored_information"] = persistent_information
        elif final_graph_message_obj and isinstance(final_graph_message_obj, AIMessage) and \
             hasattr(final_graph_message_obj, 'tool_calls') and \
             final_graph_message_obj.tool_calls and \
             any(tc.get('name') == request_clarification_tool_name for tc in final_graph_message_obj.tool_calls):
            determined_intent = "clarification_request"
        elif current_turn_graph_intent: 
             determined_intent = current_turn_graph_intent

    response_payload = {
        "response": response_data_for_payload,
        "intent": determined_intent,
        "thread_id": thread_id,
        "type": "AI" if determined_intent != "error" else "Error"
    }

    if response_payload["intent"] == "error" and response_payload["type"] == "AI":
        response_payload["type"] = "Error"
    if "message" not in response_payload["response"] :
         response_payload["response"]["message"] = "An unspecified error occurred."
    if response_payload["intent"] == "error" and response_payload["response"]["message"] == "Error: Could not determine agent's final message.":
         response_payload["response"]["message"] = "Agent encountered an issue processing the request."
    
    valid_intents = ["plan_agent", "flight_agent", "information_agent", "general_qa_agent",
                     "direct_answer", "not_related", "error", "tool_result",
                     "flight_selection_confirmed", "flights_found_awaiting_selection",
                     "clarification_request", "flight_search_direct_message",
                     "unknown_tool_result_with_data", "retrieve_information"]
    if response_payload["intent"] not in valid_intents:
         print(f"Warning: Final intent '{response_payload['intent']}' is not in the expected list. Defaulting to 'general_qa_agent'.")
         response_payload["intent"] = "general_qa_agent"
    
    return response_payload 