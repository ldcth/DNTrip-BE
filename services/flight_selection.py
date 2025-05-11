import re
from datetime import datetime
from typing import Optional

def _parse_time(time_str: str) -> Optional[datetime.time]:
    """
    Parses time strings like '10:45 pm', '9:00 AM', '14:30', '9am', '5 pm'.
    Returns a datetime.time object or None if parsing fails.
    """
    time_str = time_str.strip().lower()
    
    # Attempt to convert "9am" to "9:00 am", "5 pm" to "5:00 pm"
    # Handles "9am", "9 am", "5pm", "5 pm"
    match_short_time = re.fullmatch(r"(\\d{1,2})\\s*(am|pm)", time_str)
    if match_short_time:
        time_str = f"{match_short_time.group(1)}:00 {match_short_time.group(2)}"

    formats_to_try = ["%I:%M %p", "%H:%M"]  # Handles "10:45 pm", "09:00 am", "14:30"
    for fmt in formats_to_try:
        try:
            return datetime.strptime(time_str, fmt).time()
        except ValueError:
            continue
    return None

def select_flight_for_booking(
    available_flights: list[dict],
    selection_type: str,
    selection_value: str 
) -> dict:
    """
    Selects a specific flight from a list based on structured criteria.

    Args:
        available_flights: A list of flight dictionaries.
        selection_type: Type of selection: "ordinal", "flight_id", "departure_time".
        selection_value: The value for selection (user's input).
                         - For "ordinal": "1", "2nd", "first".
                         - For "flight_id": The flight ID string e.g., "VietJet Air 1634".
                         - For "departure_time": Time string e.g., "9:00 am", "10:45 pm", "14:30", "9pm".

    Returns:
        A dictionary with "status" and either "flight" (on success) or "message".
        Possible statuses: "success", "not_found", "multiple_matches", "error_bad_input".
    """
    if not available_flights:
        return {"status": "error_no_flights", "message": "No flights available to select from."}

    found_flights = []
    normalized_selection_value = selection_value.strip().lower()

    if selection_type == "ordinal":
        ordinal_map = {
            "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
            "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
            "1st": 1, "2nd": 2, "3rd": 3, "4th": 4, "5th": 5
        }
        
        idx = -1
        if normalized_selection_value in ordinal_map:
            idx = ordinal_map[normalized_selection_value]
        else:
            try:
                # Remove "st", "nd", "rd", "th" if present after a digit, then convert to int
                cleaned_val = re.sub(r"(\\d+)(st|nd|rd|th)", r"\\1", normalized_selection_value)
                idx = int(cleaned_val)
            except ValueError:
                return {"status": "error_bad_input", "message": f"Invalid ordinal value: '{selection_value}'. Please use numbers (e.g., '1', '2nd') or words (e.g., 'first')."}

        if 1 <= idx <= len(available_flights):
            found_flights.append(available_flights[idx - 1])
        else:
            return {"status": "not_found", "message": f"Invalid selection: '{selection_value}'. Please pick a number between 1 and {len(available_flights)}."}

    elif selection_type == "flight_id":
        target_flight_id_lower = normalized_selection_value
        for flight in available_flights:
            if flight.get("flight_id", "").strip().lower() == target_flight_id_lower:
                found_flights.append(flight)
        
        if not found_flights:
             return {"status": "not_found", "message": f"No flight found with ID '{selection_value}'. Please check the ID or select by order/time."}

    elif selection_type == "departure_time":
        target_time_obj = _parse_time(selection_value) # Use original selection_value for parsing
        if not target_time_obj:
            return {"status": "error_bad_input", "message": f"Invalid time format for departure time: '{selection_value}'. Please use HH:MM AM/PM, HH:MM (24h), or e.g., '9am'."}

        for flight in available_flights:
            flight_dep_time_str = flight.get("departure_time")
            if flight_dep_time_str:
                flight_time_obj = _parse_time(flight_dep_time_str)
                if flight_time_obj and flight_time_obj == target_time_obj:
                    found_flights.append(flight)
        
        if not found_flights:
             return {"status": "not_found", "message": f"No flight found departing at '{selection_value}'. Please check the time or select by order/ID."}
    else:
        return {"status": "error_bad_input", "message": f"Unsupported selection type: '{selection_type}'."}

    # Evaluate results from successful parsing and matching attempt
    if len(found_flights) == 1:
        return {"status": "success", "flight": found_flights[0]}
    elif len(found_flights) > 1:
        # This occurs if, for instance, multiple flights share the exact same departure time
        # or (less likely) the same flight ID was somehow duplicated in the input list.
        return {
            "status": "multiple_matches",
            "message": f"Multiple flights match your criteria '{selection_value}' for {selection_type}. Please be more specific, for example, by using the flight's order number from the list.",
            "matched_flights": found_flights 
        }
    else: 
        # This case should ideally be covered by specific "not_found" messages within each selection_type block.
        # However, it acts as a fallback.
        return {"status": "not_found", "message": f"No flight could be uniquely identified with {selection_type}: '{selection_value}'."}

if __name__ == '__main__':
    # Example Usage and Test Cases
    sample_flights = [
      { "price": "$55", "date": "Mon, May 12", "flight_id": "VietJet Air 1650", "flight_time": "1h 20m", "departure_airport": "Ho Chi Minh City (SGN)", "departure_time": "10:45 pm", "arrival_airport": "Da Nang (DAD)", "arrival_time": "12:05 am", "departure_airport_code": "SGN", "arrival_airport_code": "DAD", "search_date": "2025-05-12"},
      { "price": "$39", "date": "Mon, May 12", "flight_id": "Bamboo Airways 160", "flight_time": "1h 30m", "departure_airport": "Ho Chi Minh City (SGN)", "departure_time": "4:30 pm", "arrival_airport": "Da Nang (DAD)", "arrival_time": "6:00 pm", "departure_airport_code": "SGN", "arrival_airport_code": "DAD", "search_date": "2025-05-12"},
      { "price": "$40", "date": "Mon, May 12", "flight_id": "Vietravel Airlines 680", "flight_time": "1h 20m", "departure_airport": "Ho Chi Minh City (SGN)", "departure_time": "9:05 pm", "arrival_airport": "Da Nang (DAD)", "arrival_time": "10:25 pm", "departure_airport_code": "SGN", "arrival_airport_code": "DAD", "search_date": "2025-05-12"},
      { "price": "$40", "date": "Mon, May 12", "flight_id": "VietJet Air VJ123", "flight_time": "1h 20m", "departure_airport": "Ho Chi Minh City (SGN)", "departure_time": "9:05 pm", "arrival_airport": "Da Nang (DAD)", "arrival_time": "10:25 pm", "departure_airport_code": "SGN", "arrival_airport_code": "DAD", "search_date": "2025-05-12"}, # Duplicate time
      { "price": "$45", "date": "Mon, May 12", "flight_id": "VietJet Air 1622", "flight_time": "1h 20m", "departure_airport": "Ho Chi Minh City (SGN)", "departure_time": "5:00 am", "arrival_airport": "Da Nang (DAD)", "arrival_time": "6:20 am", "departure_airport_code": "SGN", "arrival_airport_code": "DAD", "search_date": "2025-05-12"}
    ]

    test_cases = [
        ("ordinal", "1st"),
        ("ordinal", "third"),
        ("ordinal", "5"),
        ("ordinal", "6"), # Out of bounds
        ("ordinal", "zeroth"), # Invalid
        ("flight_id", "Bamboo Airways 160"),
        ("flight_id", "NonExistent ID"),
        ("flight_id", "vietjet air 1650"), # Case-insensitivity test
        ("departure_time", "4:30 pm"),
        ("departure_time", "05:00 am"), # Leading zero test
        ("departure_time", "9:05 PM"),   # Case-insensitivity for AM/PM
        ("departure_time", "10:45PM"),  # No space before PM
        ("departure_time", "11:00 am"), # Not found
        ("departure_time", "9:05 pm"),   # Multiple matches test
        ("departure_time", "5am"),       # Short time format
        ("departure_time", "13 o'clock"), # Invalid time format for this parser
        ("unknown_type", "some value") # Bad type
    ]

    print("--- Running select_flight_for_booking Test Cases ---")
    for sel_type, sel_val in test_cases:
        print(f"\\nTesting: type='{sel_type}', value='{sel_val}'")
        result = select_flight_for_booking(sample_flights, sel_type, sel_val)
        print(result)
        if result['status'] == 'success':
            print(f"Selected Flight ID: {result['flight']['flight_id']}")
        elif result['status'] == 'multiple_matches':
            print(f"Matched {len(result['matched_flights'])} flights.")


    print("\\n--- Testing _parse_time ---")
    time_tests = ["10:45 pm", "9:00 AM", "14:30", "9am", "5 pm", "10 pm", "05:30", "5:30pm", "badtime"]
    for t_str in time_tests:
        print(f"Parsing '{t_str}': {_parse_time(t_str)}") 