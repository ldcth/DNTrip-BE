from typing import List, Dict, Any, Optional
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.language_models import BaseChatModel
import logging

# --- Configuration ---
# Adjust these thresholds as needed
SUMMARIZATION_MSG_THRESHOLD = 12 # Summarize if more than this many messages (excluding system prompt)
PRUNING_MSG_THRESHOLD = 15       # Prune if more than this many messages (excluding system prompt)
RECENT_MSGS_TO_KEEP = 5          # How many recent messages to always keep during summarization/pruning

# --- Summarization Strategy ---

def summarize_conversation_history(
    messages: List[BaseMessage],
    llm: BaseChatModel,
    threshold: int = SUMMARIZATION_MSG_THRESHOLD,
    keep_recent: int = RECENT_MSGS_TO_KEEP
) -> List[BaseMessage]:
    """
    Summarizes older parts of the conversation history if it exceeds a threshold.

    Args:
        messages: The current list of messages.
        llm: The language model to use for summarization.
        threshold: The number of messages (excluding system prompt) above which summarization occurs.
        keep_recent: The number of recent messages to keep outside the summary.

    Returns:
        A potentially summarized list of messages.
    """
    if not messages:
        return []

    system_prompt: Optional[SystemMessage] = None
    if isinstance(messages[0], SystemMessage):
        system_prompt = messages[0]
        run_messages = messages[1:]
    else:
        run_messages = messages

    if len(run_messages) <= threshold:
        logging.debug("Message count below threshold, skipping summarization.")

        return messages # No summarization needed

    logging.info(f"Message count ({len(run_messages)}) exceeds threshold ({threshold}), attempting summarization.")

    # Separate messages to summarize and messages to keep
    messages_to_summarize = run_messages[:-keep_recent]
    messages_to_keep = run_messages[-keep_recent:]

    if not messages_to_summarize:
        logging.warning("Summarization triggered, but no messages identified to summarize.")
        return messages # Should not happen with threshold logic, but safety check

    summarization_prompt = HumanMessage(
        content="""Please summarize the key information and decisions made in the preceding conversation messages. Focus on details relevant to the user's travel planning goals (e.g., requested duration, dates, origin/destination, specific interests mentioned, flight details discussed). Be concise. The summary will be used as context for the ongoing conversation.

CONVERSATION TO SUMMARIZE:
""" + "\n".join([f"{type(m).__name__}: {m.content}" for m in messages_to_summarize])
    )

    try:
        # Use a separate, potentially cheaper/faster model for summarization if desired
        summary_response = llm.invoke([summarization_prompt])
        summary_text = summary_response.content
        summary_message = AIMessage(content=f"Summary of earlier conversation: {summary_text}")
        logging.info("Summarization successful.")

        # Construct the new message list
        new_messages = []
        if system_prompt:
            new_messages.append(system_prompt)
        new_messages.append(summary_message)
        new_messages.extend(messages_to_keep)
        return new_messages

    except Exception as e:
        logging.error(f"Error during conversation summarization: {e}")
        # Fallback: Return original messages if summarization fails
        return messages


# --- Selective Pruning Strategy ---

def prune_conversation_history(
    messages: List[BaseMessage],
    max_messages: int = PRUNING_MSG_THRESHOLD,
    keep_recent: int = RECENT_MSGS_TO_KEEP
) -> List[BaseMessage]:
    """
    Prunes the conversation history if it exceeds a maximum message count,
    attempting to keep the system prompt, the first user message,
    tool interactions, and recent messages.

    Args:
        messages: The current list of messages.
        max_messages: The maximum number of messages (excluding system prompt) to keep.
        keep_recent: The number of recent messages to always keep.

    Returns:
        A potentially pruned list of messages.
    """
    if not messages:
        return []

    system_prompt: Optional[SystemMessage] = None
    first_human_message: Optional[HumanMessage] = None
    if isinstance(messages[0], SystemMessage):
        system_prompt = messages[0]
        run_messages = messages[1:]
    else:
        run_messages = messages

    if len(run_messages) <= max_messages:
        logging.debug("Message count below threshold, skipping pruning.")
        return messages # No pruning needed

    logging.info(f"Message count ({len(run_messages)}) exceeds threshold ({max_messages}), attempting pruning.")

    messages_to_consider = run_messages[:-keep_recent]
    recent_messages = run_messages[-keep_recent:]

    if not messages_to_consider:
        return messages # Should not happen, safety check

    # Identify messages to keep from the older part
    kept_older_messages = []
    # Keep the very first human message (often contains the initial request)
    if messages_to_consider and isinstance(messages_to_consider[0], HumanMessage):
         first_human_message = messages_to_consider[0]
         kept_older_messages.append(first_human_message)

    # Keep tool calls and their results (can be important context)
    for msg in messages_to_consider[1:]: # Skip first human message if already added
        if isinstance(msg, (ToolMessage, AIMessage)) and hasattr(msg, 'tool_calls') and msg.tool_calls:
             kept_older_messages.append(msg)
        elif isinstance(msg, ToolMessage): # Keep standalone tool messages too
             kept_older_messages.append(msg)


    # Combine kept messages, ensuring no duplicates and respecting order where possible
    # This is a simple approach; more sophisticated logic could be added
    final_kept_older = []
    seen_ids = set()
    if first_human_message:
        final_kept_older.append(first_human_message)
        if hasattr(first_human_message, 'id'): seen_ids.add(first_human_message.id)

    for msg in kept_older_messages:
        msg_id = getattr(msg, 'id', None)
        if msg_id and msg_id in seen_ids:
            continue
        final_kept_older.append(msg)
        if msg_id: seen_ids.add(msg_id)


    # Construct the new message list
    new_messages = []
    if system_prompt:
        new_messages.append(system_prompt)

    # Add a placeholder if messages were pruned
    if len(final_kept_older) < len(messages_to_consider):
         # Using AIMessage as a placeholder, could use a custom class
         new_messages.append(AIMessage(content="[... older messages pruned ...]"))

    new_messages.extend(final_kept_older)
    new_messages.extend(recent_messages)

    # Final check if we are still over budget (e.g., too many tool calls kept)
    # If so, apply simple truncation from the start (after system prompt and placeholder)
    current_run_messages = new_messages[1:] if system_prompt else new_messages
    if len(current_run_messages) > max_messages:
        logging.warning(f"Pruning still resulted in {len(current_run_messages)} messages (max {max_messages}). Truncating further.")
        over_limit = len(current_run_messages) - max_messages
        # Remove messages after system prompt / placeholder until limit is met
        start_index = 1 if system_prompt else 0
        start_index += 1 if "[... older messages pruned ...]" in new_messages[start_index].content else 0
        
        del new_messages[start_index : start_index + over_limit]


    logging.info(f"Pruning complete. Kept {len(new_messages)} messages total.")
    return new_messages

# Example Usage (Conceptual - Don't run directly here)
# if __name__ == '__main__':
#     # Assume 'sample_messages' is a list of BaseMessage objects
#     # Assume 'chat_model' is an instance of a BaseChatModel
#     # Needs actual message objects and model for real testing
#
#     # summarized = summarize_conversation_history(sample_messages, chat_model)
#     # print("Summarized:", summarized)
#
#     # pruned = prune_conversation_history(sample_messages)
#     # print("Pruned:", pruned)
#     pass
