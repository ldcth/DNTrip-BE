import json
import os

def fix_phone_numbers():
    """
    Corrects phone numbers that are actually plus codes in the combined data file.
    """
    script_dir = os.path.dirname(__file__)
    data_file = os.path.join(script_dir, 'data', 'combined_data.json')

    if not os.path.exists(data_file):
        print(f"Data file not found: {data_file}")
        return

    try:
        with open(data_file, 'r', encoding='utf-8') as f:
            places = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error reading {data_file}: {e}")
        return

    corrected_count = 0
    special_chars = ['\n', '\n']
    
    for place in places:
        phone = place.get('phone')
        if isinstance(phone, str):
            for char in special_chars:
                if phone.startswith(char):
                    place['phone'] = 'N/A'
                    corrected_count += 1
                    break  # Move to the next place once corrected

    try:
        with open(data_file, 'w', encoding='utf-8') as f:
            json.dump(places, f, ensure_ascii=False, indent=2)
    except IOError as e:
        print(f"Error writing to {data_file}: {e}")
        return

    print(f"Data cleaning complete. Corrected {corrected_count} entries in {data_file}")

if __name__ == "__main__":
    fix_phone_numbers() 